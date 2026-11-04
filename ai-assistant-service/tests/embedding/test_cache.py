import numpy as np
import pytest

from app.rag.embedding.base import Embedder
from app.rag.embedding.cache import CachedEmbedder, DiskEmbeddingCache
from app.rag.embedding.fake import FakeEmbedder
from app.rag.embedding.models import EmbedKind


@pytest.fixture
def temp_cache(tmp_path):
    db_file = tmp_path / "test_embeddings.db"
    return DiskEmbeddingCache(db_file)


def test_cached_embedder_protocol_compliance(temp_cache):
    inner = FakeEmbedder()
    cached = CachedEmbedder(inner, temp_cache)
    assert isinstance(cached, Embedder)
    assert cached.model_id == inner.model_id
    assert cached.dimensions == inner.dimensions
    assert cached.max_input_tokens == inner.max_input_tokens


def test_cache_query_second_call_hits_cache(temp_cache):
    inner = FakeEmbedder()
    cached = CachedEmbedder(inner, temp_cache)

    q = "iade sartlari nelerdir"
    v1 = cached.embed_query(q)
    assert inner.call_count == 1
    assert cached.hits == 0
    assert cached.misses == 1

    # İkinci çağrı: inner çağrılmamalı, hit artmalı
    v2 = cached.embed_query(q)
    assert inner.call_count == 1
    assert cached.hits == 1
    assert cached.misses == 1
    assert np.allclose(v1, v2)


def test_cache_documents_partial_misses(temp_cache):
    inner = FakeEmbedder()
    cached = CachedEmbedder(inner, temp_cache)

    docs_first = ["doc 1", "doc 2"]
    cached.embed_documents(docs_first)
    assert inner.call_count == 1
    assert inner.texts_seen == 2
    assert cached.misses == 2

    # Karışık liste: doc 1 ve doc 2 cache'te, doc 3 yeni
    docs_mixed = ["doc 1", "doc 3", "doc 2"]
    out = cached.embed_documents(docs_mixed)

    # Inner sadece eksik olan 1 metin için çağrılmalı
    assert inner.call_count == 2
    assert inner.texts_seen == 3  # 2 + 1
    assert cached.hits == 2
    assert cached.misses == 3
    assert out.shape == (3, inner.dimensions)

    # Sıralamanın korunduğunu doğrula
    v_doc1 = cached.embed_documents(["doc 1"])[0]
    v_doc3 = cached.embed_documents(["doc 3"])[0]
    assert np.allclose(out[0], v_doc1)
    assert np.allclose(out[1], v_doc3)


def test_cache_query_and_document_keys_differ(temp_cache):
    text = "ayni metin"
    k_query = temp_cache.build_key("model", 256, EmbedKind.QUERY, text)
    k_doc = temp_cache.build_key("model", 256, EmbedKind.DOCUMENT, text)
    assert k_query != k_doc


def test_cache_different_model_ids_differ(temp_cache):
    text = "ayni metin"
    k_m1 = temp_cache.build_key("model-a", 256, EmbedKind.QUERY, text)
    k_m2 = temp_cache.build_key("model-b", 256, EmbedKind.QUERY, text)
    assert k_m1 != k_m2


def test_cache_corrupted_or_empty_cache_graceful(tmp_path):
    # Boş / geçersiz dosya
    bad_db = tmp_path / "bad.db"
    bad_db.write_text("corrupted content", encoding="utf-8")
    cache = DiskEmbeddingCache(bad_db)

    # get ve get_many hata fırlatmak yerine None / {} dönmeli
    assert cache.get("nonexistent_key", 256) is None
    assert cache.get_many(["k1", "k2"], 256) == {}


def test_cache_write_error_logged(tmp_path, caplog):
    import logging

    bad_db = tmp_path / "bad.db"
    bad_db.write_text("corrupted content", encoding="utf-8")
    cache = DiskEmbeddingCache(bad_db)

    with caplog.at_level(logging.WARNING):
        # Bozuk DB'ye set veya set_many çağrısı çökmemeli ancak uyarı loglamalıdır
        cache.set("key1", np.zeros(256, dtype=np.float32))
        cache.set_many([("key2", np.zeros(256, dtype=np.float32))])

    assert "Failed to write to embedding cache" in caplog.text
