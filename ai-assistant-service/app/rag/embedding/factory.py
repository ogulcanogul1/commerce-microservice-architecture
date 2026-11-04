"""Factory function for creating and caching embedder instances."""

from app.rag.embedding.base import Embedder
from app.rag.embedding.cache import CachedEmbedder, DiskEmbeddingCache
from app.rag.embedding.fake import FakeEmbedder
from app.rag.embedding.models import EmbeddingConfig
from app.rag.embedding.providers.gemini_embedder import GeminiEmbedder
from app.rag.embedding.providers.local_embedder import LocalEmbedder
from app.rag.embedding.providers.openai_embedder import OpenAIEmbedder


def get_embedder(
    config: EmbeddingConfig,
    *,
    cache: DiskEmbeddingCache | None = None,
) -> Embedder:
    """Create an Embedder instance according to the configuration.

    If a DiskEmbeddingCache is supplied, returns a CachedEmbedder wrapping the instance.
    Raises ValueError on unknown provider name.
    """
    provider = config.provider.lower().strip()

    if provider == "openai":
        embedder: Embedder = OpenAIEmbedder(config)
    elif provider == "gemini":
        embedder = GeminiEmbedder(config)
    elif provider == "local":
        embedder = LocalEmbedder(config)
    elif provider == "fake":
        dim = config.dimensions or 256
        embedder = FakeEmbedder(dimensions=dim, model_id=config.model_id())
    else:
        raise ValueError(
            f"Unknown embedding provider: '{config.provider}'. "
            f"Supported providers: openai, gemini, local, fake."
        )

    if cache is not None:
        return CachedEmbedder(embedder, cache)

    return embedder
