from unittest.mock import MagicMock
import numpy as np
import pytest

from app.rag.embedding.base import Embedder
from app.rag.embedding.factory import get_embedder
from app.rag.embedding.models import EmbeddingConfig
from app.rag.embedding.providers.gemini_embedder import GeminiEmbedder
from app.rag.embedding.providers.local_embedder import LocalEmbedder
from app.rag.embedding.providers.openai_embedder import OpenAIEmbedder


class MockOpenAIItem:
    def __init__(self, embedding: list[float]):
        self.embedding = embedding


class MockOpenAIResponse:
    def __init__(self, data: list[MockOpenAIItem]):
        self.data = data


def test_openai_embedder_mocked():
    mock_client = MagicMock()
    mock_client.embeddings.create.return_value = MockOpenAIResponse(
        [
            MockOpenAIItem([0.6, 0.8]),
            MockOpenAIItem([0.0, 1.0]),
        ]
    )

    cfg = EmbeddingConfig(
        provider="openai",
        model="text-embedding-3-small",
        dimensions=2,
        batch_size=2,
    )
    embedder = OpenAIEmbedder(config=cfg, client=mock_client)

    assert isinstance(embedder, Embedder)
    assert embedder.dimensions == 2
    assert embedder.model_id == "openai/text-embedding-3-small@2"

    docs = ["chunk 1", "chunk 2"]
    out = embedder.embed_documents(docs)

    assert out.shape == (2, 2)
    assert out.dtype == np.float32
    mock_client.embeddings.create.assert_called_once()
    call_kwargs = mock_client.embeddings.create.call_args[1]
    assert call_kwargs["model"] == "text-embedding-3-small"
    assert call_kwargs["dimensions"] == 2
    assert call_kwargs["input"] == ["chunk 1", "chunk 2"]

    # Boş metin reddi
    with pytest.raises(ValueError):
        embedder.embed_documents(["   "])
    with pytest.raises(ValueError):
        embedder.embed_query("")


class MockGeminiEmbedding:
    def __init__(self, values: list[float]):
        self.values = values


class MockGeminiResponse:
    def __init__(self, embeddings: list[MockGeminiEmbedding]):
        self.embeddings = embeddings


def test_gemini_embedder_mocked():
    mock_client = MagicMock()
    mock_client.models.embed_content.return_value = MockGeminiResponse(
        [
            MockGeminiEmbedding([0.6, 0.8]),
        ]
    )

    cfg = EmbeddingConfig(
        provider="gemini",
        model="text-embedding-004",
        dimensions=2,
    )
    embedder = GeminiEmbedder(config=cfg, client=mock_client)

    assert isinstance(embedder, Embedder)

    # Document embedding -> RETRIEVAL_DOCUMENT
    out_docs = embedder.embed_documents(["metin"])
    assert out_docs.shape == (1, 2)
    call_args = mock_client.models.embed_content.call_args[1]
    assert call_args["config"].task_type == "RETRIEVAL_DOCUMENT"
    assert call_args["config"].output_dimensionality == 2

    # Query embedding -> RETRIEVAL_QUERY
    out_query = embedder.embed_query("sorgu")
    assert out_query.shape == (2,)
    call_args_q = mock_client.models.embed_content.call_args[1]
    assert call_args_q["config"].task_type == "RETRIEVAL_QUERY"

    # Boş metin reddi
    with pytest.raises(ValueError):
        embedder.embed_query("   ")


def test_local_embedder_e5_prefix_and_mock():
    mock_client = MagicMock()
    mock_client.embeddings.create.return_value = MockOpenAIResponse(
        [
            MockOpenAIItem([0.6, 0.8]),
        ]
    )

    cfg = EmbeddingConfig(
        provider="local",
        model="multilingual-e5-small",
        dimensions=2,
    )
    embedder = LocalEmbedder(config=cfg, client=mock_client)

    # Doküman için 'passage: ' öneki kontrolü
    embedder.embed_documents(["dokuman metni"])
    call_kwargs_doc = mock_client.embeddings.create.call_args[1]
    assert call_kwargs_doc["input"] == ["passage: dokuman metni"]

    # Sorgu için 'query: ' öneki kontrolü
    embedder.embed_query("sorgu metni")
    call_kwargs_query = mock_client.embeddings.create.call_args[1]
    assert call_kwargs_query["input"] == ["query: sorgu metni"]


def test_local_embedder_bge_m3_no_prefix():
    mock_client = MagicMock()
    mock_client.embeddings.create.return_value = MockOpenAIResponse(
        [
            MockOpenAIItem([0.6, 0.8]),
        ]
    )

    cfg = EmbeddingConfig(
        provider="local",
        model="bge-m3",
        dimensions=2,
    )
    embedder = LocalEmbedder(config=cfg, client=mock_client)
    assert not embedder.is_e5

    embedder.embed_documents(["bge dokuman"])
    call_kwargs = mock_client.embeddings.create.call_args[1]
    assert call_kwargs["input"] == ["bge dokuman"]


def test_factory_get_embedder(tmp_path):
    from app.rag.embedding.cache import CachedEmbedder, DiskEmbeddingCache

    # Fake provider
    cfg_fake = EmbeddingConfig(provider="fake", model="test-fake", dimensions=128)
    emb_fake = get_embedder(cfg_fake)
    assert isinstance(emb_fake, Embedder)
    assert emb_fake.dimensions == 128

    # CachedEmbedder wrapper
    cache = DiskEmbeddingCache(tmp_path / "cache.db")
    emb_cached = get_embedder(cfg_fake, cache=cache)
    assert isinstance(emb_cached, CachedEmbedder)
    assert emb_cached.dimensions == 128

    # Bilinmeyen provider
    cfg_unknown = EmbeddingConfig(provider="unknown_provider", model="x")
    with pytest.raises(ValueError, match="Unknown embedding provider"):
        get_embedder(cfg_unknown)


def test_get_default_embedder(monkeypatch):
    from app.core.config import settings
    from app.rag.embedding import get_default_embedder
    from app.rag.embedding.fake import FakeEmbedder

    monkeypatch.setattr(settings, "EMBEDDING_PROVIDER", "fake")
    monkeypatch.setattr(settings, "EMBEDDING_MODEL", "default-test")
    monkeypatch.setattr(settings, "EMBEDDING_DIMENSIONS", 64)

    embedder = get_default_embedder()
    assert isinstance(embedder, FakeEmbedder)
    assert embedder.dimensions == 64

