from collections.abc import Sequence
from typing import Protocol
from app.rag.rerank.models import RerankResult


class Reranker(Protocol):
    """Tüm reranker sağlayıcılarının uyması gereken senkron protokol."""

    model_id: str  # Raporlarda ve loglarda görünecek model kimliği (örn: "fake-reranker", "cohere/rerank-v3.5")

    def rerank(self, query: str, documents: Sequence[str]) -> list[RerankResult]:
        """SENKRON rerank metodu.

        - Tüm documents için skor üretir.
        - Skora göre AZALAN sıralı döner.
        - Eşit skorlarda orijinal sıra korunur (Stable sorting).
        - Boş documents verilirse boş liste döner.
        - Hata durumunda yalnızca RerankError fırlatır (iç istisnalar sızdırılmaz).
        """
        ...
