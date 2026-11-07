from typing import Any
from app.rag.rerank.base import Reranker


def get_reranker(provider: str, model_name: str | None = None) -> Reranker:
    """Belirtilen sağlayıcı string'ine göre Reranker örneği üretir."""
    norm_provider = provider.lower().strip()

    if norm_provider == "fake":
        from app.rag.rerank.fake import FakeReranker

        return FakeReranker(model_id=f"fake/{model_name}" if model_name else "fake-reranker")

    if norm_provider == "cross_encoder":
        from app.rag.rerank.cross_encoder import CrossEncoderReranker

        return CrossEncoderReranker(model_name=model_name or "")

    if norm_provider == "cohere":
        from app.rag.rerank.cohere import CohereReranker

        return CohereReranker(model_name=model_name or "")

    raise ValueError(
        f"Bilinmeyen reranker sağlayıcısı: '{provider}'. "
        "Geçerli seçenekler: 'cross_encoder', 'cohere', 'fake'"
    )


def build_reranker_from_settings(settings: Any) -> Reranker | None:
    """Uygulama ayarlarından Reranker örneğini oluşturur.

    RAG_RERANK_ENABLED=False ise None döner ve hiçbir sağlayıcı modülü import edilmez.
    """
    if not getattr(settings, "RAG_RERANK_ENABLED", False):
        return None

    provider = getattr(settings, "RAG_RERANK_PROVIDER", "cross_encoder")
    model_name = getattr(settings, "RAG_RERANK_MODEL", "")
    return get_reranker(provider, model_name or None)
