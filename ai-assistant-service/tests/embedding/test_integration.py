"""Integration tests making real API calls when credentials are available."""

import pytest

from app.core.config import settings
from app.rag.embedding.models import EmbeddingConfig
from app.rag.embedding.providers.gemini_embedder import GeminiEmbedder
from app.rag.embedding.providers.local_embedder import LocalEmbedder
from app.rag.embedding.providers.openai_embedder import OpenAIEmbedder


@pytest.mark.integration
def test_openai_embedder_live():
    if not settings.OPENAI_API_KEY:
        pytest.skip("OPENAI_API_KEY is not set; skipping live integration test.")

    cfg = EmbeddingConfig(
        provider="openai",
        model="text-embedding-3-small",
        dimensions=256,
    )
    embedder = OpenAIEmbedder(config=cfg)

    texts = ["Turkiye e-ticaret lojistik", "Kargo takip sorgulama"]
    docs_matrix = embedder.embed_documents(texts)
    assert docs_matrix.shape == (2, 256)

    query_vec = embedder.embed_query("siparis nerede")
    assert query_vec.shape == (256,)


@pytest.mark.integration
def test_gemini_embedder_live():
    if not settings.GEMINI_API_KEY:
        pytest.skip("GEMINI_API_KEY is not set; skipping live integration test.")

    cfg = EmbeddingConfig(
        provider="gemini",
        model="text-embedding-004",
        dimensions=256,
    )
    embedder = GeminiEmbedder(config=cfg)

    texts = ["Turkiye e-ticaret lojistik", "Kargo takip sorgulama"]
    docs_matrix = embedder.embed_documents(texts)
    assert docs_matrix.shape == (2, 256)

    query_vec = embedder.embed_query("siparis nerede")
    assert query_vec.shape == (256,)


@pytest.mark.integration
def test_local_embedder_live():
    if not settings.LOCAL_LLM_BASE_URL:
        pytest.skip("LOCAL_LLM_BASE_URL is not set; skipping live local server test.")

    # Yerel sunucunun (örn. Ollama) ayakta olup olmadığını doğrula, ayakta değilse beklemeden skip et
    import urllib.request

    try:
        urllib.request.urlopen(settings.LOCAL_LLM_BASE_URL, timeout=0.5)
    except Exception:
        pytest.skip(f"Local LLM server at {settings.LOCAL_LLM_BASE_URL} is unreachable.")

    cfg = EmbeddingConfig(
        provider="local",
        model="intfloat/multilingual-e5-small",
        dimensions=256,
    )
    embedder = LocalEmbedder(config=cfg)

    texts = ["Turkiye e-ticaret lojistik", "Kargo takip sorgulama"]
    docs_matrix = embedder.embed_documents(texts)
    assert docs_matrix.shape == (2, 256)

    query_vec = embedder.embed_query("siparis nerede")
    assert query_vec.shape == (256,)
