from collections.abc import Sequence
from pydantic import BaseModel, ConfigDict


class RerankResult(BaseModel):
    """Tek bir dokümanın reranker skorunu ve orijinal konumunu temsil eder."""

    model_config = ConfigDict(frozen=True)

    index: int  # Girdi documents listesindeki orijinal konum (0..n-1)
    score: float  # Reranker alaka skoru (yüksek = daha alakalı)


class RerankError(Exception):
    """Reranker çağrısı başarısız oldu (zaman aşımı, sağlayıcı hatası, geçersiz cevap)."""

    pass


def validate_rerank_results(results: Sequence[RerankResult], n: int) -> None:
    """Reranker sonuçlarının sözleşmeye (contract) uygunluğunu doğrular.

    Kurallar:
    1. Sonuç sayısı tam olarak girdi doküman sayısı (n) kadar olmalıdır.
    2. Her index 0 ile n-1 aralığında olmalıdır.
    3. Hiçbir index tekrarlanmamalı (duplicate) ve hiçbir index eksik kalmamalıdır.
    """
    if len(results) != n:
        raise RerankError(
            f"Reranker eksik veya fazla sonuç döndürdü: beklenen {n}, gelen {len(results)}"
        )

    seen_indices: set[int] = set()
    for res in results:
        if res.index < 0 or res.index >= n:
            raise RerankError(f"Reranker geçersiz index döndürdü: {res.index} (aralık: 0..{n-1})")
        if res.index in seen_indices:
            raise RerankError(f"Reranker yinelenen index döndürdü: {res.index}")
        seen_indices.add(res.index)
