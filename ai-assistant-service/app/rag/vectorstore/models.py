"""Qdrant vektör deposu için veri modelleri ve konfigürasyon."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Literal
from pydantic import BaseModel, Field

from app.rag.chunking.models import Chunk

if TYPE_CHECKING:
    from app.rag.embedding.base import Embedder


def _slugify(text: str) -> str:
    """Metni yalnızca küçük harf, rakam ve alt çizgi içeren bir slug'a dönüştürür."""
    # Harf ve rakam dışındaki tüm karakterleri alt çizgiye dönüştür
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", text).strip("_").lower()
    # Ardışık birden fazla alt çizgiyi tek alt çizgiye indir
    return re.sub(r"_+", "_", slug)


class QdrantConfig(BaseModel):
    """Qdrant istemcisi ve koleksiyon yönetimi için dondurulmuş (immutable) konfigürasyon."""

    url: str = Field(default="http://localhost:6333", description="Qdrant REST URL")
    api_key: str | None = Field(default=None, description="Qdrant API anahtarı (varsa)")
    collection_prefix: str = Field(default="commerce_docs", description="Koleksiyon ön eki")
    upsert_batch_size: int = Field(default=128, ge=1, description="Toplu yazma boyutu")
    timeout_sec: float = Field(default=30.0, gt=0, description="İstek zaman aşımı (saniye)")

    model_config = {"frozen": True}

    def collection_name(self, embedder: Embedder) -> str:
        """Embedder özelliklerine (model_id, boyut) göre tekil koleksiyon adı üretir.

        Örnek format: {prefix}__{model_id_slug}_{dimensions}
        Örnek çıktı: commerce_docs__openai_text_embedding_3_small_1536
        """
        model_slug = _slugify(embedder.model_id)
        dim = embedder.dimensions
        return f"{self.collection_prefix}__{model_slug}_{dim}"


class SearchHit(BaseModel):
    """Vektör veya hibrit arama sonucu dönen tekil eşleşme."""

    chunk: Chunk = Field(description="Eşleşen doküman parçası")
    score: float = Field(description="Arama benzerlik skoru (Cosine veya RRF fusion)")
    source: Literal["dense", "sparse", "hybrid"] = Field(
        description="Sonucun hangi arama yönteminden geldiği"
    )

    model_config = {"frozen": True}


class SyncReport(BaseModel):
    """Incremental sync işlemi sonucunda üretilen özet rapor."""

    created: int = Field(default=0, description="Yeni oluşturulan doküman sayısı")
    skipped: int = Field(default=0, description="Değişmediği için atlanan doküman sayısı")
    replaced: int = Field(default=0, description="Güncellenen doküman sayısı")
    pruned: int = Field(default=0, description="Klasörde olmadığı için silinen doküman sayısı")
    failed: list[tuple[str, str]] = Field(
        default_factory=list,
        description="İşlenemeyen dosyalar ve hata gerekçeleri: (dosya_yolu, hata_mesaji)",
    )

    def total_processed(self) -> int:
        """İşleme alınan (başarılı) toplam dosya sayısı."""
        return self.created + self.skipped + self.replaced
