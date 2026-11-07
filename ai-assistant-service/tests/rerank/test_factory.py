import sys
from types import SimpleNamespace
import pytest
from app.rag.rerank.cross_encoder import CrossEncoderReranker
from app.rag.rerank.factory import build_reranker_from_settings, get_reranker
from app.rag.rerank.fake import FakeReranker


def test_get_reranker_fake():
    r = get_reranker("fake")
    assert isinstance(r, FakeReranker)
    assert r.model_id == "fake-reranker"

    r_custom = get_reranker("fake", "smoke-test")
    assert isinstance(r_custom, FakeReranker)
    assert r_custom.model_id == "fake/smoke-test"


def test_get_reranker_cross_encoder():
    r = get_reranker("cross_encoder", "BAAI/bge-reranker-base")
    assert isinstance(r, CrossEncoderReranker)
    assert r.model_name == "BAAI/bge-reranker-base"


def test_get_reranker_unknown_raises():
    with pytest.raises(ValueError, match="Bilinmeyen reranker sağlayıcısı"):
        get_reranker("unsupported_provider")


def test_build_reranker_from_settings_disabled(monkeypatch):
    # sentence_transformers veya cohere import edilmemeli
    monkeypatch.delitem(sys.modules, "sentence_transformers", raising=False)

    settings = SimpleNamespace(
        RAG_RERANK_ENABLED=False,
        RAG_RERANK_PROVIDER="cross_encoder",
        RAG_RERANK_MODEL="",
    )
    reranker = build_reranker_from_settings(settings)
    assert reranker is None
    assert "sentence_transformers" not in sys.modules


def test_build_reranker_from_settings_enabled():
    settings = SimpleNamespace(
        RAG_RERANK_ENABLED=True,
        RAG_RERANK_PROVIDER="fake",
        RAG_RERANK_MODEL="my-model",
    )
    reranker = build_reranker_from_settings(settings)
    assert isinstance(reranker, FakeReranker)
    assert reranker.model_id == "fake/my-model"
