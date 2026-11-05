"""Qdrant vektör veritabanı yönetim ve yazma katmanı (QdrantStore).

Bu modül, Qdrant istemcisi ile doğrudan etkileşime girerek şu temel sorumlulukları üstlenir:
  1. Çift vektörlü (Named Vectors: 'dense' + 'sparse') koleksiyon şemasını kurma ve boyut doğrulama.
  2. Filtreleme sorgularını milisaniyelere indiren payload indekslerini (B-Tree/Keyword) açma.
  3. Doküman parçalarını (Chunk), dense vektörleri ve otomatik üretilen BM25 sparse vektörleri ile
     birlikte partiler halinde (batching) veritabanına yazma (upsert).
  4. Doküman güncellemelerinde veri kaybını önleyen "Upsert-then-Delete" mantığıyla eski point'leri silme (delete_stale).
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
    """Qdrant vektör deposu için koleksiyon oluşturma, indeksleme ve yazma yöneticisi.

    Bu sınıf doğrudan Qdrant sunucusuyla (veya bellek içi ':memory:' istemcisiyle)
    haberleşir. 'dense' (anlamsal arama) ve 'sparse' (BM25 kelime araması) olmak
    üzere iki vektör alanı açar. Arama (search) mantığı bu sınıfta yer almaz; bu
    sınıf yalnızca depolama, güncelleme ve silme (CRUD) işlemlerinden sorumludur.
    """

    def __init__(
        self,
        client: QdrantClient,
        config: QdrantConfig,
        embedder: Embedder | None = None,
        sparse_encoder: SparseEncoder | None = None,
        collection_name: str | None = None,
    ) -> None:
        """QdrantStore başlatıcı metodu.

        Args:
            client: Qdrant istemcisi (gerçek HTTP/gRPC sunucu veya testler için ':memory:').
            config: Qdrant ayarları (batch boyutu, koleksiyon ön eki, timeout).
            embedder: Boyut ve model adını öğrenmek için kullanılan Embedder nesnesi (opsiyonel).
            sparse_encoder: Metinleri BM25 sparse vektörlerine dönüştüren kodlayıcı (varsayılan: SparseEncoder()).
            collection_name: Özel koleksiyon adı (belirtilmezse embedder modelinden otomatik türetilir).
        """
        self.client = client
        self.config = config
        self.embedder = embedder
        # Eğer dışarıdan bir sparse_encoder verilmediyse varsayılan ayarlarla oluştur
        self.sparse_encoder = sparse_encoder or SparseEncoder()

        # Koleksiyon adını belirle: Özel isim verilmişse onu al, yoksa embedder'dan türet
        self._collection_name = collection_name
        if not self._collection_name and self.embedder is not None:
            self._collection_name = self.config.collection_name(self.embedder)

    @property
    def collection_name(self) -> str:
        """Etkin koleksiyon adını döner.

        Eğer koleksiyon adı henüz bilinmiyorsa ve embedder tanımlıysa otomatik türetir;
        hiçbiri yoksa fail-fast prensibiyle açıkça ValueError fırlatır.

        Returns:
            Koleksiyon adı string'i (örn: 'commerce_docs__openai_text_embedding_3_small_1536').
        """
        if not self._collection_name:
            if self.embedder is not None:
                self._collection_name = self.config.collection_name(self.embedder)
            else:
                raise ValueError(
                    "Koleksiyon adı henüz belirlenmemiş. "
                    "Lütfen 'ensure_collection(embedder)' çağırın veya başlangıçta bir embedder sağlayın."
                )
        return self._collection_name

    def ensure_collection(
        self,
        embedder: Embedder | None = None,
        collection_name: str | None = None,
    ) -> str:
        """Koleksiyon yoksa Qdrant'ta oluşturur; varsa vektör boyutunu doğrular.

        İşlem Adımları:
          1. Hedef embedder ve koleksiyon adı tespit edilir.
          2. client.collection_exists(col_name) ile veritabanı kontrol edilir.
          3. Koleksiyon ZATEN VARSA:
             - Mevcut koleksiyonun 'dense' vektör boyutu kontrol edilir.
             - Eğer veritabanındaki boyut (örn. 768) ile embedder'ın boyutu (örn. 1536)
               uyuşmuyorsa, verilerin bozulmasını önlemek için ValueError fırlatılır (Karar 5).
          4. Koleksiyon YOKSA:
             - client.create_collection çağrılarak iki adet adlandırılmış vektör açılır:
               a) 'dense': Boyut = embedder.dimensions, Uzaklık Metriği = Cosine
               b) 'sparse': Qdrant sunucu taraflı BM25 IDF hesaplayıcı (Modifier.IDF)

        Args:
            embedder: Boyut ve model bilgisi alınacak embedder. Sağlanmazsa self.embedder kullanılır.
            collection_name: Özel bir koleksiyon adı kullanılmak istenirse belirtilir.

        Returns:
            Oluşturulan veya doğrulanmış koleksiyon adı (str).
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

        # 1. Adım: Koleksiyon veritabanında zaten mevcut mu?
        if self.client.collection_exists(col_name):
            info = self.client.get_collection(col_name)
            existing_dim = None

            # Qdrant yapılandırmasından 'dense' vektörünün boyutunu oku
            vectors_param = info.config.params.vectors
            if isinstance(vectors_param, dict) and "dense" in vectors_param:
                existing_dim = vectors_param["dense"].size
            elif hasattr(vectors_param, "size"):
                existing_dim = vectors_param.size

            # Boyut uyuşmazlığı kontrolü (Karar 5: Sessizce ezme yok, fail-fast)
            if existing_dim is not None and existing_dim != dim:
                raise ValueError(
                    f"Koleksiyon boyutu uyuşmazlığı: '{col_name}' koleksiyonu {existing_dim} boyutunda, "
                    f"ancak embedder {dim} boyutunda vektörler bekliyor. "
                    "Eski verilerin bozulmasını önlemek için farklı bir model/boyut koleksiyonu kullanılmalıdır."
                )
            return col_name  # Boyutlar uyumlu, mevcut koleksiyon adı döndürülür

        # 2. Adım: Koleksiyon yoksa çift vektörlü (dense + sparse) olarak oluştur
        self.client.create_collection(
            collection_name=col_name,
            # Dense Vektör: Semantik anlam araması için Cosine uzaklığı
            vectors_config={
                "dense": models.VectorParams(
                    size=dim,
                    distance=models.Distance.COSINE,
                )
            },
            # Sparse Vektör: BM25 anahtar kelime araması ve sunucu taraflı IDF hesabı
            sparse_vectors_config={
                "sparse": models.SparseVectorParams(
                    modifier=models.Modifier.IDF,
                )
            },
            timeout=self.config.timeout_sec,
        )
        return col_name

    def ensure_payload_indexes(self) -> None:
        """Sorgularda filtreleme hızını artırmak için payload alanlarına indeks tanımlar.

        PostgreSQL'deki 'CREATE INDEX' komutuna benzer şekilde çalışır.
        İndekslenen alanlar:
          - source_file (KEYWORD): 'source_file = "sozlesme.pdf"' filtreleri için.
          - doc_hash (KEYWORD): Doküman güncellemelerinde eski point'leri tek sorguda silmek için.
          - page_start (INTEGER): 'page_start >= 1 AND page_start <= 3' aralık filtreleri için.
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
                # İndeks zaten mevcutsa veya yerel ':memory:' modu uyarı verirse görmezden gel
                pass

    def upsert_chunks(
        self,
        chunks: Sequence[Chunk],
        dense_vectors: Sequence[Sequence[float]] | np.ndarray,
        doc_hash: str,
        ingested_at: str | None = None,
    ) -> int:
        """Doküman parçalarını (Chunk) vektörleri ve metadata'sı ile birlikte Qdrant'a yazar.

        İşlem Adımları:
          1. EŞİTLİK DOĞRULAMASI: Her 1 Chunk için tam olarak 1 adet Dense Vektör olmalıdır.
             (len(chunks) != len(dense_vectors) ise kayma/eşleşme hatası olmaması için fail-fast yapılır).
          2. METADATA VE SPARSE HESABI:
             - Her chunk'ın metninden SparseEncoder ile BM25 (indices, values) üretilir.
             - chunk.id'den deterministik uuid5 point kimliği oluşturulur.
             - chunk_to_payload ile disk tasarruflu (embedding_text hariç) payload hazırlanır.
          3. TOPLU YAZMA (BATCHING):
             - Point'ler config.upsert_batch_size (örn: 128) boyutundaki gruplara bölünür.
             - client.upsert(..., wait=True) ile veritabanına yazılır.

        Args:
            chunks: Eklenecek doküman parçaları listesi.
            dense_vectors: Embedder tarafından bu chunk'lar için üretilmiş float vektörler.
            doc_hash: Dokümanın o anki içeriğinin benzersiz parmak izi (fingerprint).
            ingested_at: İsteğe bağlı ISO-8601 zaman damgası (boşsa anlık UTC zamanı).

        Returns:
            Veritabanına yazılan toplam point sayısı (int).
        """
        # 1. Adım: Birebir eşleşme güvencesi (1 Chunk = 1 Dense Vector)
        if len(chunks) != len(dense_vectors):
            raise ValueError(
                f"Chunk sayısı ({len(chunks)}) ile dense vektör sayısı ({len(dense_vectors)}) eşit olmalıdır."
            )

        if not chunks:
            return 0  # Yazılacak veri yoksa 0 dön

        col_name = self.collection_name
        now_iso = ingested_at or datetime.now(timezone.utc).isoformat()
        embedder_model_id = self.embedder.model_id if self.embedder else "unknown"

        # 2. Adım: Qdrant PointStruct nesnelerini oluştur
        points: list[models.PointStruct] = []
        for chunk, dense_vec in zip(chunks, dense_vectors):
            # Deterministik UUID point kimliği (Karar 1)
            pid = chunk_point_id(chunk.id)

            # Chunk metninden BM25 sparse vektörünü üret
            sparse_indices, sparse_values = self.sparse_encoder.encode_document(chunk.embedding_text)

            # Numpy dizisi geldiyse standart Python listesine çevir
            dense_list = dense_vec.tolist() if isinstance(dense_vec, np.ndarray) else list(dense_vec)

            # Chunk modelini JSON payload'a çevir (embedding_text hariç tutularak disk tasarrufu sağlanır)
            payload = chunk_to_payload(
                chunk,
                doc_hash=doc_hash,
                embedding_model_id=embedder_model_id,
                ingested_at=now_iso,
            )

            # Hem dense hem sparse vektörü tek bir point içinde birleştir
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

        # 3. Adım: Partiler halinde (Batching) Qdrant'a gönder (wait=True: diske yazılana kadar bekle)
        for batch in batched(points, self.config.upsert_batch_size):
            self.client.upsert(
                collection_name=col_name,
                points=list(batch),
                wait=True,
            )

        return len(points)  # Toplam yazılan point sayısı döner

    def delete_stale(self, source_file: str, keep_doc_hash: str) -> None:
        """Güncellenen bir dokümanın eski versiyonuna ait point'leri siler.

        Karar 7 (Upsert-then-Delete Prensibi):
          Önce yeni versiyonun chunk'ları 'upsert_chunks' ile veritabanına yazılır.
          İşlem başarıyla tamamlandıktan sonra bu metot çağrılarak:
            - source_file == source_file (Sadece bu dosya)
            - doc_hash != keep_doc_hash (Yeni hash DIŞINDAKİ tüm eski versiyonlar)
          şartını sağlayan point'ler tek seferde silinir.
          Bu sayede güncelleme sırasında sistem çökse dahi eski veriler kaybolmaz!

        Args:
            source_file: Temizlenecek dokümanın dosya yolu/adı (örn: 'sozlesme.pdf').
            keep_doc_hash: Muhafaza edilecek (silinmeyecek) güncel doküman karması.
        """
        col_name = self.collection_name
        # Filtre: Bu dosyaya ait olsun (must) AMA güncel hash'e sahip olmasın (must_not)
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
        """Belirtilen source_file'a ait tüm parçaları koleksiyondan tamamen siler.

        Bir PDF sistemden tamamen kaldırıldığında veya silindiğinde kullanılır.

        Args:
            source_file: Silinecek dokümanın dosya adı (örn: 'eski_kampanya.pdf').
        """
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
        """Koleksiyondaki toplam veya belirli bir dosyaya ait point (vektör) sayısını döner.

        Args:
            source_file: Belirtilirse sadece o dosyanın point'leri sayılır; boşsa tüm koleksiyon.

        Returns:
            Kayıtlı point sayısı (int).
        """
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

        # exact=True: Tahmini değil, kesin gerçek sayıyı döner
        res = self.client.count(
            collection_name=col_name,
            count_filter=count_filter,
            exact=True,
        )
        return res.count

    def get_doc_hash(self, source_file: str) -> str | None:
        """Koleksiyonda o dosyaya ait kayıtlı doc_hash (parmak izi) değerini okur.

        Neden Scroll Kullanılıyor?
          Tüm dokümanı veya tüm vektörleri bellekten çekmek yerine,
          Qdrant'ın 'scroll' API'si ile sadece 1 adet point'in 'doc_hash' alanını
          okur (limit=1, with_payload=['doc_hash']). Bu sayede sıfır ağ/bellek yüküyle
          dokümanın değişip değişmediği kontrol edilir.

        Args:
            source_file: Kontrol edilecek doküman yolu (örn: 'sozlesme.pdf').

        Returns:
            Dokümanın kayıtlı doc_hash değeri (str) veya doküman/koleksiyon yoksa None.
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
        # Sadece 1 kayıt çek ve sadece 'doc_hash' payload alanını getir
        points, _ = self.client.scroll(
            collection_name=col_name,
            scroll_filter=doc_filter,
            limit=1,
            with_payload=["doc_hash"],
        )
        if points and points[0].payload:
            return points[0].payload.get("doc_hash")
        return None
