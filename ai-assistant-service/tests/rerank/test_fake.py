import pytest
from app.rag.rerank.fake import FakeReranker
from app.rag.rerank.models import RerankError


def test_fake_reranker_with_explicit_scores():
    reranker = FakeReranker(scores=[0.1, 0.9, 0.5])
    results = reranker.rerank("herhangi bir soru", ["doc0", "doc1", "doc2"])

    assert len(results) == 3
    # Skorlara göre azalan sıra: doc1 (0.9), doc2 (0.5), doc0 (0.1)
    assert results[0].index == 1
    assert results[0].score == 0.9
    assert results[1].index == 2
    assert results[1].score == 0.5
    assert results[2].index == 0
    assert results[2].score == 0.1


def test_fake_reranker_word_overlap():
    reranker = FakeReranker()
    docs = [
        "Kargo teslimat süresi standart 3 iş günüdür.",
        "İade politikası gereği 14 gün içinde ürünler iade edilebilir.",
        "Müşteri hizmetleri çalışma saatleri 09:00 - 18:00 arasıdır.",
    ]
    query = "İade süresi kaç gün?"
    results = reranker.rerank(query, docs)

    assert len(results) == 3
    # En yüksek kelime örtüşmesi 1 numaralı dokümanda ("iade", "gün")
    assert results[0].index == 1
    assert results[0].score > results[1].score


def test_fake_reranker_stable_sorting_on_tie():
    # doc0 ve doc1 eşit skor (0.8), doc2 daha düşük (0.2)
    reranker = FakeReranker(scores=[0.8, 0.8, 0.2])
    results = reranker.rerank("soru", ["d0", "d1", "d2"])

    assert results[0].index == 0
    assert results[1].index == 1
    assert results[2].index == 2


def test_fake_reranker_empty_documents():
    reranker = FakeReranker()
    results = reranker.rerank("soru", [])
    assert results == []


def test_fake_reranker_records_calls():
    reranker = FakeReranker()
    reranker.rerank("ilk soru", ["d1", "d2"])
    reranker.rerank("ikinci soru", ["d3"])

    assert len(reranker.calls) == 2
    assert reranker.calls[0] == {"query": "ilk soru", "documents": ["d1", "d2"]}
    assert reranker.calls[1] == {"query": "ikinci soru", "documents": ["d3"]}


def test_fake_reranker_raise_on_call():
    reranker_custom = FakeReranker(raise_on_call=ValueError("bağlantı koptu"))
    with pytest.raises(RerankError, match="Fake rerank failure: bağlantı koptu"):
        reranker_custom.rerank("soru", ["d1"])

    reranker_direct = FakeReranker(raise_on_call=RerankError("özel hata"))
    with pytest.raises(RerankError, match="özel hata"):
        reranker_direct.rerank("soru", ["d1"])


def test_fake_reranker_scores_mismatch_raises():
    reranker = FakeReranker(scores=[0.1, 0.2])  # 2 skor verildi ama 3 doküman istendi
    with pytest.raises(RerankError, match="scores uzunluğu"):
        reranker.rerank("soru", ["d1", "d2", "d3"])


def test_fake_reranker_turkish_casing():
    reranker = FakeReranker()
    doc = "Ürün iade koşulları"
    # Büyük İADE ile küçük iade aynı örtüşmeyi üretmeli
    results_upper = reranker.rerank("İADE", [doc])
    results_lower = reranker.rerank("iade", [doc])

    assert results_upper[0].score == results_lower[0].score
    assert results_upper[0].score > 0.0
