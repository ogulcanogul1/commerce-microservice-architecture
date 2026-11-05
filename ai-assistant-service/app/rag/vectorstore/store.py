"""Qdrant vektör veritabanı yönetim ve yazma katmanı (QdrantStore).

Bu modül, Qdrant istemcisi ile doğrudan etkileşime girerek:
  1. Çift vektörlü (dense + sparse) koleksiyon oluşturma ve boyut doğrulama,
  2. Arama performansını artıran payload indekslerini kurma,
  3. Doküman parçalarını (Chunk) vektörleri ile birlikte toplu (batch) yazma,
  4. Doküman güncellemelerinde eski versiyonları temizleme (delete_stale)
sorumluluklarını yerine getirir.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Sequence
import numpy as np
from qdrant_client import QdrantClient, models

from app.rag.chunking.models import Chunk
from app.rag.embedding.base import Embedder
from app.rag.embedding.batching import batched
from app.rag.vectorstore.mapping import chunk_point_id, chunk_to_payload
from app.rag.vectorstore.models import QdrantConfig
from app.rag.vectorstore.sparse import SparseEncoder


class QdrantStore:
    """Qdrant vektör deposu için koleksiyon, indeksleme ve yazma yöneticisi.

    Bu sınıf doğrudan Qdrant sunucusuyla (veya bellek içi ':memory:' istemcisiyle)
    konuşur. Dense (vektör) ve Sparse (BM25) olmak üzere iki adlandırılmış vektör
    şeması kurar. Arama mantığı bu sınıfta yer almaz; bu sınıf yalnızca depolama,
    güncelleme ve silme (CRUD) işlemlerinden sorumludur.
    """

    def __init__(
        self,
        client: QdrantClient,
        config: QdrantConfig,
        embedder: Embedder | None = None,
        sparse_encoder: SparseEncoder | None = None,
        collection_name: str | None = None,
    ) -> None:
        """QdrantStore başlatıcı.

        Args:
            client: QdrantClient örneği (bağlantı kurulmuş sunucu veya ':memory:').
            config: Qdrant konfigürasyon nesnesi (batch_size, prefix, timeout).
            embedder: Vektör boyutu ve adlandırma için Embedder nesnesi (opsiyonel).
            sparse_encoder: BM25 sparse vektör kodlayıcısı (varsayılan: SparseEncoder()).
            collection_name: Koleksiyon adı (boşsa embedder üzerinden dinamik türetilir).
        """
        self.client = client
        self.config = config
        self.embedder = embedder
        self.sparse_encoder = sparse_encoder or SparseEncoder()
        self._collection_name = collection_name
        if not self._collection_name and self.embedder is not None:
            self._collection_name = self.config.collection_name(self.embedder)

    @property
    def collection_name(self) -> str:
        """Etkin koleksiyon adını döner. Tanımlı değilse açık hata fırlatır."""
        if not self._collection_name:
            if self.embedder is not None:
                self._collection_name = self.config.collection_name(self.embedder)
            else:
                raise ValueError(
                    "Koleksiyon adı henüz belirlenmemiş. "
                    "Lütfen 'ensure_collection(embedder)' çağırın veya başlatıcıda bir embedder sağlayın."
                )
        return self._collection_name

    def ensure_collection(
        self,
        embedder: Embedder | None = None,
        collection_name: str | None = None,
    ) -> str:
        """Koleksiyon yoksa oluşturur; varsa vektör boyutunu doğrular.

        Karar 5: Koleksiyon adı embedder'a göre dinamiktir ({prefix}__{model_slug}_{dim})
        veya doğrudan collection_name parametresiyle sabitlenebilir.
        Eğer aynı isimde bir koleksiyon zaten varsa, mevcut koleksiyonun boyutu kontrol edilir.
        Boyut uyuşmazlığı varsa sessizce yeniden oluşturmak yerine açık hata verir.

        Args:
            embedder: Boyut ve model bilgisi alınacak embedder. Sağlanmazsa self.embedder kullanılır.
            collection_name: Özel koleksiyon adı (opsiyonel).

        Returns:
            Oluşturulan veya doğrulanan koleksiyonun adı (str).

        Raises:
            ValueError: Mevcut koleksiyonun vektör boyutu ile embedder boyutu uyuşmuyorsa.
        """
        target_embedder = embedder or self.embedder
        if target_embedder is None:
            raise ValueError("Koleksiyon oluşturmak için bir embedder gereklidir.")

        self.embedder = target_embedder
        if collection_name:
            self._collection_name = collection_name
        elif not self._collection_name:
            self._collection_name = self.config.collection_name(target_embedder)

        col_name = self._collection_name
        dim = target_embedder.dimensions

        # Koleksiyon zaten mevcut mu?
        if self.client.collection_exists(col_name):
            info = self.client.get_collection(col_name)
            # Mevcut dense vektör boyutunu doğrula
            existing_dim = None
            vectors_param = info.config.params.vectors
            if isinstance(vectors_param, dict) and "dense" in vectors_param:
                existing_dim = vectors_param["dense"].size
            elif hasattr(vectors_param, "size"):
                existing_dim = vectors_param.size

            if existing_dim is not None and existing_dim != dim:
                raise ValueError(
                    f"Koleksiyon boyutu uyuşmazlığı: '{col_name}' koleksiyonu {existing_dim} boyutunda, "
                    f"ancak embedder {dim} boyutunda vektörler bekliyor. "
                    "Eski verilerin bozulmasını önlemek için farklı bir model/boyut koleksiyonu kullanılmalıdır."
                )
            return col_name

        # Koleksiyon yoksa: named dense + sparse vektör şemasıyla oluştur
        self.client.create_collection(
            collection_name=col_name,
            vectors_config={
                "dense": models.VectorParams(
                    size=dim,
                    distance=models.Distance.COSINE,
                )
            },
            sparse_vectors_config={
                "sparse": models.SparseVectorParams(
                    modifier=models.Modifier.IDF,
                )
            },
            timeout=self.config.timeout_sec,
        )
        return col_name

    def ensure_payload_indexes(self) -> None:
        """Filtreleme performansını artırmak için payload alanlarına indeks tanımlar.

        İndekslenen alanlar:
          - source_file (KEYWORD): Dosya bazlı filtrelemeler için.
          - doc_hash (KEYWORD): Eski doküman parçalarını tek sorguda bulup silmek için.
          - page_start (INTEGER): Sayfa aralığı filtrelemeleri için.
        """
        col_name = self.collection_name
        indexes = [
            ("source_file", models.PayloadSchemaType.KEYWORD),
            ("doc_hash", models.PayloadSchemaType.KEYWORD),
            ("page_start", models.PayloadSchemaType.INTEGER),
        ]
        for field_name, field_schema in indexes:
            try:
                self.client.create_payload_index(
                    collection_name=col_name,
                    field_name=field_name,
                    field_schema=field_schema,
                )
            except Exception:
                # İndeks zaten mevcutsa veya yerel bellek uyarısı gelirse yoksay
                pass

    def upsert_chunks(
        self,
        chunks: Sequence[Chunk],
        dense_vectors: Sequence[Sequence[float]] | np.ndarray,
        doc_hash: str,
        ingested_at: str | None = None,
    ) -> int:
        """Chunk'ları dense ve sparse vektörleri ile birlikte Qdrant'a yazar.

        İşlem Adımları:
          1. Chunk sayısı ile dense vektör sayısının eşitliği doğrulanır.
          2. Her chunk için SparseEncoder ile BM25 sparse vektörü hesaplanır.
          3. PointStruct nesneleri oluşturulur (id = uuid5(chunk.id)).
          4. upsert_batch_size partilerine bölünerek Qdrant'a gönderilir.

        Args:
            chunks: Eklenecek doküman parçaları.
            dense_vectors: Her bir chunk için hesaplanmış dense float vektörler.
            doc_hash: Dokümanın güncel içerik karması (fingerprint).
            ingested_at: ISO-8601 zaman damgası (boşsa şu anki UTC zamanı).

        Returns:
            Yazılan toplam chunk sayısı (int).
        """
        if len(chunks) != len(dense_vectors):
            raise ValueError(
                f"Chunk sayısı ({len(chunks)}) ile dense vektör sayısı ({len(dense_vectors)}) eşit olmalıdır."
            )

        if not chunks:
            return 0

        col_name = self.collection_name
        now_iso = ingested_at or datetime.now(timezone.utc).isoformat()
        embedder_model_id = self.embedder.model_id if self.embedder else "unknown"

        points: list[models.PointStruct] = []
        for chunk, dense_vec in zip(chunks, dense_vectors):
            pid = chunk_point_id(chunk.id)
            # Sparse BM25 vektörünü chunk metninden otomatik hesapla
            sparse_indices, sparse_values = self.sparse_encoder.encode_document(chunk.embedding_text)

            # Dense vektörü liste formatına getir
            dense_list = dense_vec.tolist() if isinstance(dense_vec, np.ndarray) else list(dense_vec)

            payload = chunk_to_payload(
                chunk,
                doc_hash=doc_hash,
                embedding_model_id=embedder_model_id,
                ingested_at=now_iso,
            )

            point = models.PointStruct(
                id=pid,
                vector={
                    "dense": dense_list,
                    "sparse": models.SparseVector(
                        indices=sparse_indices,
                        values=sparse_values,
                    ),
                },
                payload=payload,
            )
            points.append(point)

        # upsert_batch_size partilerine bölerek Qdrant'a bas (wait=True: işlem tamamlanana kadar bekle)
        for batch in batched(points, self.config.upsert_batch_size):
            self.client.upsert(
                collection_name=col_name,
                points=list(batch),
                wait=True,
            )

        return len(points)

    def delete_stale(self, source_file: str, keep_doc_hash: str) -> None:
        """Hedef dosyaya ait, ancak güncel doc_hash ile uyuşmayan eski point'leri siler.

        Karar 7 (Upsert-then-Delete): Önce yeni chunk'lar başarıyla yazılır,
        ardından bu metot çağrılarak eski versiyona ait point'ler temizlenir.
        Böylece çökme veya elektrik kesintisi anında veri kaybı yaşanmaz.
        """
        col_name = self.collection_name
        filter_stale = models.Filter(
            must=[
                models.FieldCondition(
                    key="source_file",
                    match=models.MatchValue(value=source_file),
                )
            ],
            must_not=[
                models.FieldCondition(
                    key="doc_hash",
                    match=models.MatchValue(value=keep_doc_hash),
                )
            ],
        )
        self.client.delete(
            collection_name=col_name,
            points_selector=models.FilterSelector(filter=filter_stale),
            wait=True,
        )

    def delete_document(self, source_file: str) -> None:
        """Belirtilen source_file'a ait tüm point'leri koleksiyondan tamamen siler."""
        col_name = self.collection_name
        doc_filter = models.Filter(
            must=[
                models.FieldCondition(
                    key="source_file",
                    match=models.MatchValue(value=source_file),
                )
            ]
        )
        self.client.delete(
            collection_name=col_name,
            points_selector=models.FilterSelector(filter=doc_filter),
            wait=True,
        )

    def count(self, source_file: str | None = None) -> int:
        """Koleksiyondaki toplam veya belirli bir dosyaya ait point sayısını döner."""
        col_name = self.collection_name
        count_filter = None
        if source_file:
            count_filter = models.Filter(
                must=[
                    models.FieldCondition(
                        key="source_file",
                        match=models.MatchValue(value=source_file),
                    )
                ]
            )

        res = self.client.count(
            collection_name=col_name,
            count_filter=count_filter,
            exact=True,
        )
        return res.count

    def get_doc_hash(self, source_file: str) -> str | None:
        """Koleksiyonda o dosyaya ait kayıtlı doc_hash değerini döner.

        Returns:
            Kayıtlı hash string'i veya dosya/koleksiyon yoksa None.
        """
        col_name = self.collection_name
        if not self.client.collection_exists(col_name):
            return None

        doc_filter = models.Filter(
            must=[
                models.FieldCondition(
                    key="source_file",
                    match=models.MatchValue(value=source_file),
                )
            ]
        )
        points, _ = self.client.scroll(
            collection_name=col_name,
            scroll_filter=doc_filter,
            limit=1,
            with_payload=["doc_hash"],
        )
        if points and points[0].payload:
            return points[0].payload.get("doc_hash")
        return None
