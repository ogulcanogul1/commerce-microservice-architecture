import numpy as np

from app.rag.embedding.base import Embedder
from app.rag.embedding.fake import FakeEmbedder


def test_fake_embedder_protocol_compliance():
    embedder = FakeEmbedder()
    assert isinstance(embedder, Embedder)
    assert embedder.dimensions == 256
    assert embedder.max_input_tokens == 512


def test_fake_embedder_deterministic():
    embedder = FakeEmbedder()
    vec1 = embedder.embed_query("sipariş kargo takip")
    vec2 = embedder.embed_query("sipariş kargo takip")
    assert np.allclose(vec1, vec2)


def test_fake_embedder_semantic_similarity():
    embedder = FakeEmbedder()
    q = embedder.embed_query("sipariş kargo takip")

    # Benzer doküman: ortak kelimeler var
    doc_similar = embedder.embed_query("kargo takip ve teslimat süreci")
    # Alakasız doküman: hiç ortak kelime yok
    doc_unrelated = embedder.embed_query("elma armut portakal muz meyve")

    sim_high = float(np.dot(q, doc_similar))
    sim_low = float(np.dot(q, doc_unrelated))

    assert sim_high > sim_low
    assert sim_high > 0.0


def test_fake_embedder_shapes_and_types():
    embedder = FakeEmbedder(dimensions=128)
    q_vec = embedder.embed_query("deneme")
    assert q_vec.shape == (128,)
    assert q_vec.dtype == np.float32
    assert np.isclose(np.linalg.norm(q_vec), 1.0)

    docs = ["ilk metin", "ikinci metin", "ucuncu metin"]
    doc_matrix = embedder.embed_documents(docs)
    assert doc_matrix.shape == (3, 128)
    assert doc_matrix.dtype == np.float32
    norms = np.linalg.norm(doc_matrix, axis=1)
    assert np.allclose(norms, [1.0, 1.0, 1.0])


def test_fake_embedder_empty_inputs():
    embedder = FakeEmbedder()
    empty_docs = embedder.embed_documents([])
    assert empty_docs.shape == (0, 256)

    # Noktalama veya boşluk içeren metin (token çıkmayan)
    empty_query = embedder.embed_query("   !!! ???   ")
    assert empty_query.shape == (256,)
    assert np.all(empty_query == 0.0)


def test_fake_embedder_call_counters():
    embedder = FakeEmbedder()
    assert embedder.call_count == 0
    assert embedder.texts_seen == 0

    embedder.embed_query("test 1")
    assert embedder.call_count == 1
    assert embedder.texts_seen == 1

    embedder.embed_documents(["doc 1", "doc 2", "doc 3"])
    assert embedder.call_count == 2
    assert embedder.texts_seen == 4
