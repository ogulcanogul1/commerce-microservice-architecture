"""Factory function for creating and caching embedder instances."""

from app.rag.embedding.base import Embedder
from app.rag.embedding.cache import CachedEmbedder, DiskEmbeddingCache
from app.rag.embedding.fake import FakeEmbedder
from app.rag.embedding.models import EmbeddingConfig, EmbeddingProvider
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
    prov_str = config.provider.value if isinstance(config.provider, EmbeddingProvider) else str(config.provider).lower().strip()

    try:
        provider_enum = EmbeddingProvider(prov_str)
    except ValueError:
        valid_options = ", ".join([p.value for p in EmbeddingProvider])
        raise ValueError(
            f"Unknown embedding provider: '{config.provider}'. "
            f"Supported providers: {valid_options}."
        )

    match provider_enum:
        case EmbeddingProvider.OPENAI:
            embedder: Embedder = OpenAIEmbedder(config)
        case EmbeddingProvider.GEMINI:
            embedder = GeminiEmbedder(config)
        case EmbeddingProvider.LOCAL:
            embedder = LocalEmbedder(config)
        case EmbeddingProvider.FAKE:
            dim = config.dimensions or 256
            embedder = FakeEmbedder(dimensions=dim, model_id=config.model_id())

    if cache is not None:
        return CachedEmbedder(embedder, cache)

    return embedder
