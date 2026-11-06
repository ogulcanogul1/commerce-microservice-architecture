"""Qdrant vektör arama fonksiyonları (Dense, Sparse ve RRF Hybrid).

Bu modül, Qdrant sunucusunda 3 farklı arama yöntemini çalıştırır:
  1. search_dense: Anlamsal benzerlik araması (Cosine similarity).
  2. search_sparse: Anahtar kelime araması (BM25 sparse dot-product).
  3. search_hybrid: İki yöntemi sunucu tarafında Prefetch + Reciprocal Rank Fusion (RRF)
     ile birleştiren modern hibrit arama.
"""

from __future__ import annotations

from typing import Sequence
import numpy as np
from pydantic import BaseModel, Field
from qdrant_client import QdrantClient, models

from app.rag.chunking.models import Chunk
from app.rag.vectorstore.mapping import payload_to_chunk
from app.rag.vectorstore.models import SearchHit


class SearchFilter(BaseModel):
    """Arama sorgularını daraltmak için kullanılan filtre modeli.

    Özellikler:
      - source_file: Yalnızca belirli bir doküman içinde arama yapmak için (örn: 'sozlesme.pdf').
      - page_start / page_end: Belirli sayfa aralığına kısıtlamak için.
    """

    source_file: str | None = Field(default=None, description="Doküman dosya adı filtresi")
    page_start: int | None = Field(default=None, ge=1, description="Başlangıç sayfası (dahil)")
    page_end: int | None = Field(default=None, ge=1, description="Bitiş sayfası (dahil)")

    model_config = {"frozen": True}

    def to_qdrant_filter(self) -> models.Filter | None:
        """Pydantic modelini Qdrant'ın anlayacağı models.Filter nesnesine dönüştürür.

        Filtre koşulu yoksa None döner.
        """
        conditions: list[models.FieldCondition] = []

        # Dosya adı filtresi
        if self.source_file:
            conditions.append(
                models.FieldCondition(
                    key="source_file",
                    match=models.MatchValue(value=self.source_file),
                )
            )

        # Sayfa aralığı filtresi
        # Not: Chunk'ın [page_start, page_end] aralığı içinde kalmasını doğrulamak için:
        # page_start >= self.page_start ve page_end <= self.page_end kontrolü yapılır.
        if self.page_start is not None and self.page_end is not None:
            conditions.append(
                models.FieldCondition(
                    key="page_start",
                    range=models.Range(gte=float(self.page_start)),
                )
            )
            conditions.append(
                models.FieldCondition(
                    key="page_end",
                    range=models.Range(lte=float(self.page_end)),
                )
            )
        elif self.page_start is not None:
            conditions.append(
                models.FieldCondition(
                    key="page_start",
                    range=models.Range(gte=float(self.page_start)),
                )
            )
        elif self.page_end is not None:
            conditions.append(
                models.FieldCondition(
                    key="page_end",
                    range=models.Range(lte=float(self.page_end)),
                )
            )

        if not conditions:
            return None

        return models.Filter(must=conditions)


def search_dense(
    client: QdrantClient,
    collection_name: str,
    query_vec: Sequence[float] | np.ndarray,
    k: int = 5,
    filter: SearchFilter | models.Filter | None = None,
) -> list[SearchHit]:
    """Dense (anlamsal) vektör araması yapar.

    Args:
        client: QdrantClient örneği.
        collection_name: Hedef koleksiyon adı.
        query_vec: Sorgu metninin embedding vektörü (float listesi).
        k: İstenen en iyi sonuç sayısı (varsayılan: 5).
        filter: Opsiyonel SearchFilter veya Qdrant Filter nesnesi.

    Returns:
        SearchHit nesnelerinden oluşan liste (score büyükten küçüğe sıralı).
    """
    if k <= 0:
        return []

    q_filter = filter.to_qdrant_filter() if isinstance(filter, SearchFilter) else filter
    dense_list = query_vec.tolist() if isinstance(query_vec, np.ndarray) else list(query_vec)

    # Qdrant Query API ile 'dense' adlandırılmış vektöründe arama yap
    res = client.query_points(
        collection_name=collection_name,
        query=dense_list,
        using="dense",
        query_filter=q_filter,
        limit=k,
        with_payload=True,
    )

    hits: list[SearchHit] = []
    for point in res.points:
        if point.payload:
            chunk = payload_to_chunk(point.payload)
            hits.append(SearchHit(chunk=chunk, score=float(point.score or 0.0), source="dense"))
    return hits


def search_sparse(
    client: QdrantClient,
    collection_name: str,
    query_sparse: tuple[list[int], list[float]] | models.SparseVector,
    k: int = 5,
    filter: SearchFilter | models.Filter | None = None,
) -> list[SearchHit]:
    """Sparse (BM25 anahtar kelime) araması yapar.

    Args:
        client: QdrantClient örneği.
        collection_name: Hedef koleksiyon adı.
        query_sparse: (indices, values) demeti veya models.SparseVector nesnesi.
        k: İstenen en iyi sonuç sayısı.
        filter: Opsiyonel filtre.

    Returns:
        SearchHit listesi (anahtar kelime skoru yüksekten düşüğe).
    """
    if k <= 0:
        return []

    # SparseVector nesnesini hazırla
    if isinstance(query_sparse, tuple):
        indices, values = query_sparse
        if not indices:
            return []  # Sorguda hiç geçerli kelime yoksa boş liste dön
        sparse_vec = models.SparseVector(indices=indices, values=values)
    else:
        sparse_vec = query_sparse
        if not sparse_vec.indices:
            return []

    q_filter = filter.to_qdrant_filter() if isinstance(filter, SearchFilter) else filter

    # Qdrant Query API ile 'sparse' adlandırılmış vektöründe arama yap
    res = client.query_points(
        collection_name=collection_name,
        query=sparse_vec,
        using="sparse",
        query_filter=q_filter,
        limit=k,
        with_payload=True,
    )

    hits: list[SearchHit] = []
    for point in res.points:
        if point.payload:
            chunk = payload_to_chunk(point.payload)
            hits.append(SearchHit(chunk=chunk, score=float(point.score or 0.0), source="sparse"))
    return hits


def search_hybrid(
    client: QdrantClient,
    collection_name: str,
    query_vec: Sequence[float] | np.ndarray,
    query_sparse: tuple[list[int], list[float]] | models.SparseVector,
    k: int = 5,
    filter: SearchFilter | models.Filter | None = None,
) -> list[SearchHit]:
    """Dense ve Sparse aramayı sunucu tarafında RRF (Reciprocal Rank Fusion) ile birleştiren hibrit arama.

    İşlem Adımları (Karar 2):
      1. Prefetch limiti belirlenir: max(k * 4, 20) -> İki listeden de yeterli aday toplanır.
      2. Dense Prefetch: query_vec ile anlam adayları çekilir.
      3. Sparse Prefetch: query_sparse ile anahtar kelime adayları çekilir.
      4. FusionQuery(fusion=Fusion.RRF): Qdrant sunucusu iki sıralamayı formülle birleştirir:
         RRF_score(d) = 1 / (60 + rank_dense(d)) + 1 / (60 + rank_sparse(d))
      5. En yüksek RRF skoruna sahip ilk k aday tek bir liste olarak döndürülür.

    Args:
        client: QdrantClient örneği.
        collection_name: Hedef koleksiyon adı.
        query_vec: Dense sorgu float vektörü.
        query_sparse: Sparse (indices, values) sorgu vektörü.
        k: Döndürülecek nihai sonuç sayısı.
        filter: Opsiyonel filtre.

    Returns:
        SearchHit listesi (source="hybrid").
    """
    if k <= 0:
        return []

    q_filter = filter.to_qdrant_filter() if isinstance(filter, SearchFilter) else filter
    dense_list = query_vec.tolist() if isinstance(query_vec, np.ndarray) else list(query_vec)

    # Sparse vektörü hazırla
    if isinstance(query_sparse, tuple):
        indices, values = query_sparse
        has_sparse = bool(indices)
        sparse_vec = models.SparseVector(indices=indices, values=values) if has_sparse else None
    else:
        has_sparse = bool(query_sparse.indices)
        sparse_vec = query_sparse if has_sparse else None

    # Eğer sorguda hiç anahtar kelime yoksa (örn. sadece semboller girilmişse), dense aramaya geri dön
    if not has_sparse or sparse_vec is None:
        hits = search_dense(client, collection_name, query_vec, k=k, filter=q_filter)
        return [
            SearchHit(chunk=h.chunk, score=h.score, source="hybrid") for h in hits
        ]

    # Karar 2: İki Prefetch dalı için aday havuzu genişliği
    prefetch_limit = max(k * 4, 20)

    prefetch_dense = models.Prefetch(
        query=dense_list,
        using="dense",
        filter=q_filter,
        limit=prefetch_limit,
    )

    prefetch_sparse = models.Prefetch(
        query=sparse_vec,
        using="sparse",
        filter=q_filter,
        limit=prefetch_limit,
    )

    # Sunucu tarafı RRF füzyon sorgusu
    res = client.query_points(
        collection_name=collection_name,
        prefetch=[prefetch_dense, prefetch_sparse],
        query=models.FusionQuery(fusion=models.Fusion.RRF),
        limit=k,
        with_payload=True,
    )

    hits: list[SearchHit] = []
    for point in res.points:
        if point.payload:
            chunk = payload_to_chunk(point.payload)
            hits.append(SearchHit(chunk=chunk, score=float(point.score or 0.0), source="hybrid"))
    return hits
