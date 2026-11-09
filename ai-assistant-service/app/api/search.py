"""RAG Arama API Uç Noktası (POST /rag/search).

Bu modül, Qdrant vektör deposu üzerinde dense, sparse ve hibrit arama
yapan HTTP REST uç noktasını sunar.

Sorumluluklar ve Tasarım Prensipleri:
1. İstek Doğrulama: Pydantic ile sorgu uzunluğu (1..1000), k aralığı (1..20)
   ve arama modu (dense/sparse/hybrid) doğrulanır. Boş sorgular 422 ile reddedilir.
2. Bilgi İzolasyonu: Cevap modelinde dahili embedding metinleri veya karakter
   ofsetleri (char_start/char_end) yer almaz; yalnızca istemcinin ihtiyaç duyduğu
   chunk_id, score, text, source_file, sayfa bilgileri ve başlık hiyerarşisi döner.
3. Hata Yönetimi: Qdrant bağlantı hatalarında dahili URL/anahtar bilgisi sızdırılmadan
   503 Service Unavailable dönülür. Koleksiyon henüz oluşturulmamışsa 503 ile
   anlaşılır Türkçe hata mesajı iletilir.
4. Gevşek Bağlantı (Loose Coupling): FastAPI dependency injection (Depends)
   kullanılarak testlerde bellek içi (:memory:) store ve sahte embedder ile
   kolayca override edilebilir.
"""

from __future__ import annotations

import logging
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field, field_validator

from app.rag.embedding.base import Embedder
from app.rag.vectorstore.search import (
    SearchFilter,
    search_dense,
    search_hybrid,
    search_sparse,
)
from app.rag.vectorstore.store import QdrantStore

logger = logging.getLogger(__name__)

router = APIRouter(tags=["RAG Search"])


# ============================================================================
# İSTEK VE CEVAP MODELLERİ (DTO)
# ============================================================================


class SearchRequest(BaseModel):
    """RAG Arama isteği gövde modeli (POST /rag/search)."""

    query: str = Field(
        ...,
        min_length=1,
        max_length=1000,
        description="Arama yapılacak doğal dil sorgusu (boş veya yalnızca boşluk olamaz)",
        examples=["İade süresi kaç gündür?"],
    )
    k: int = Field(
        default=5,
        ge=1,
        le=20,
        description="Döndürülecek maksimum sonuç sayısı (1 ile 20 arasında)",
        examples=[5],
    )
    mode: Literal["dense", "sparse", "hybrid"] = Field(
        default="hybrid",
        description="Arama stratejisi: 'dense' (Cosine), 'sparse' (BM25) veya 'hybrid' (RRF)",
        examples=["hybrid"],
    )
    source_file: str | None = Field(
        default=None,
        description="Aramayı belirli bir dokümanla sınırlamak için kaynak dosya adı filtresi",
        examples=["sozlesme.pdf"],
    )

    @field_validator("query")
    @classmethod
    def validate_query_not_whitespace(cls, value: str) -> str:
        """Sorgunun yalnızca boşluk karakterlerinden oluşmasını engeller."""
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("Arama sorgusu boş veya yalnızca boşluklardan oluşamaz.")
        return trimmed


class SearchHitResponse(BaseModel):
    """Arama sonucunda eşleşen tekil bir doküman parçası (Chunk DTO)."""

    chunk_id: str = Field(description="Chunk tekil kimliği (hash tabanlı UUID/string)")
    score: float = Field(description="Arama benzerlik skoru (Cosine benzerliği veya RRF füzyon skoru)")
    text: str = Field(description="Chunk'ın kullanıcıya sunulacak temiz metin içeriği")
    source_file: str = Field(description="Kaynak dosya adı (örn: iade_politikasi.pdf)")
    page_start: int = Field(description="Chunk'ın başladığı sayfa numarası")
    page_end: int = Field(description="Chunk'ın bittiği sayfa numarası")
    heading_path: list[str] = Field(
        default_factory=list,
        description="Doküman başlık hiyerarşisi (örn: ['Bölüm 2', 'İade Şartları'])",
    )


class SearchResponse(BaseModel):
    """Arama API'sinin döndüğü sonuç listesi."""

    hits: list[SearchHitResponse] = Field(
        default_factory=list,
        description="En yüksek skordan en düşüğe sıralı eşleşen parçalar listesi",
    )


# ============================================================================
# BAĞIMLILIK ENJEKSİYONU (DEPENDENCY INJECTION)
# ============================================================================


def get_qdrant_store(request: Request) -> QdrantStore:
    """FastAPI Request bağlamından QdrantStore örneğini çözer.

    Lifespan sırasında app.state.qdrant_store alanına yerleştirilir.
    Testlerde `app.dependency_overrides[get_qdrant_store]` ile kolayca taklit edilebilir.
    """
    store = getattr(request.app.state, "qdrant_store", None)
    if store is None:
        logger.error("QdrantStore app.state üzerinde bulunamadı.")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Vektör deposu yapılandırılmamış veya erişilemiyor.",
        )
    return store


def get_embedder(request: Request) -> Embedder:
    """FastAPI Request bağlamından Embedder örneğini çözer.

    Lifespan sırasında app.state.embedder alanına yerleştirilir.
    Testlerde `app.dependency_overrides[get_embedder]` ile taklit edilebilir.
    """
    embedder = getattr(request.app.state, "embedder", None)
    if embedder is None:
        logger.error("Embedder app.state üzerinde bulunamadı.")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Embedding modeli yapılandırılmamış veya erişilemiyor.",
        )
    return embedder


# ============================================================================
# ARAMA UÇ NOKTASI (POST /rag/search)
# ============================================================================


@router.post(
    "/rag/search",
    response_model=SearchResponse,
    summary="Doküman parçaları üzerinde hibrit/vektör arama yapar",
    description=(
        "Kullanıcı sorgusuna en uygun doküman parçalarını Qdrant üzerinden "
        "dense (anlamsal), sparse (BM25) veya sunucu taraflı RRF hibrit füzyon ile getirir."
    ),
    responses={
        200: {"description": "Arama başarılı, eşleşen parçalar döndü."},
        422: {"description": "Geçersiz istek (boş sorgu veya k limit aşımı)."},
        503: {"description": "Vektör veritabanına erişilemiyor veya koleksiyon henüz indekslenmemiş."},
    },
)
def search_documents(
    payload: SearchRequest,
    store: QdrantStore = Depends(get_qdrant_store),  # -> app.state üzerinden Qdrant vektör koleksiyonu bağlantısını çözer
    embedder: Embedder = Depends(get_embedder),  # -> app.state üzerinden sorguyu vektörleştirecek Embedding modelini çözer
) -> SearchResponse:
    """RAG Arama işlemini yürüten ana denetleyici metot.

    Adımlar:
      1. Koleksiyon varlığı kontrol edilir (yoksa 503 "henüz indekslenmemiş").
      2. İsteğe bağlı dosya adı filtresi `SearchFilter` nesnesine sarılır.
      3. Seçilen moda ('dense', 'sparse', 'hybrid') göre arama fonksiyonu çağrılır.
      4. `SearchHit` nesneleri `SearchHitResponse` DTO'larına dönüştürülerek döner.
    """
    collection_name = store.collection_name

    # 1. Koleksiyonun Qdrant üzerinde var olup olmadığını doğrula
    try:
        exists = store.client.collection_exists(collection_name)
    except Exception as exc:
        logger.error("Qdrant koleksiyon varlığı kontrol edilirken hata: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Vektör veritabanına erişilemiyor.",
        ) from None

    if not exists:
        logger.warning("Koleksiyon '%s' henüz oluşturulmamış.", collection_name)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Vektör koleksiyonu henüz indekslenmemiş.",
        )

    # 2. Arama filtresini oluştur
    filter_obj = SearchFilter(source_file=payload.source_file) if payload.source_file else None

    # 3. Arama moduna göre arama yap
    try:
        if payload.mode == "dense":
            query_vec = embedder.embed_query(payload.query)
            hits = search_dense(
                client=store.client,
                collection_name=collection_name,
                query_vec=query_vec,
                k=payload.k,
                filter=filter_obj,
            )
        elif payload.mode == "sparse":
            query_sparse = store.sparse_encoder.encode_query(payload.query)
            hits = search_sparse(
                client=store.client,
                collection_name=collection_name,
                query_sparse=query_sparse,
                k=payload.k,
                filter=filter_obj,
            )
        else:  # hybrid
            query_vec = embedder.embed_query(payload.query)
            query_sparse = store.sparse_encoder.encode_query(payload.query)
            hits = search_hybrid(
                client=store.client,
                collection_name=collection_name,
                query_vec=query_vec,
                query_sparse=query_sparse,
                k=payload.k,
                filter=filter_obj,
            )
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Arama işlemi sırasında hata: %s", exc)
        # İç hata mesajlarını ve bağlantı ayrıntılarını istemciye sızdırmadan 503 dön
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Vektör arama işlemi sırasında bir hata oluştu.",
        ) from None

    # 4. Dahili SearchHit nesnelerini API DTO'larına dönüştür
    response_hits = [
        SearchHitResponse(
            chunk_id=hit.chunk.id,
            score=hit.score,
            text=hit.chunk.text,
            source_file=hit.chunk.source_file,
            page_start=hit.chunk.page_start,
            page_end=hit.chunk.page_end,
            heading_path=hit.chunk.heading_path,
        )
        for hit in hits
    ]

    return SearchResponse(hits=response_hits)
