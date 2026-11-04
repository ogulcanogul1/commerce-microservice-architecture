from app.rag.embedding.base import Embedder, l2_normalize
from app.rag.embedding.cache import CachedEmbedder, DiskEmbeddingCache
from app.rag.embedding.factory import get_embedder
from app.rag.embedding.fake import FakeEmbedder
from app.rag.embedding.models import EmbedKind, EmbeddingConfig, EmbeddingProvider


def get_default_embedder(cache: DiskEmbeddingCache | None = None) -> Embedder:
    """Create the default configured embedder instance from application Settings.

    Uses settings.EMBEDDING_PROVIDER, EMBEDDING_MODEL, and EMBEDDING_DIMENSIONS.
    """
    from app.core.config import settings

    config = EmbeddingConfig(
        provider=settings.EMBEDDING_PROVIDER,
        model=settings.EMBEDDING_MODEL,
        dimensions=settings.EMBEDDING_DIMENSIONS,
    )
    return get_embedder(config, cache=cache)


__all__ = [
    "Embedder",
    "l2_normalize",
    "EmbedKind",
    "EmbeddingProvider",
    "EmbeddingConfig",
    "FakeEmbedder",
    "DiskEmbeddingCache",
    "CachedEmbedder",
    "get_embedder",
    "get_default_embedder",
]
