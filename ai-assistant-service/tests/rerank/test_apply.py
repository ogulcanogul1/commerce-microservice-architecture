import logging
import pytest
from app.rag.chunking.models import Chunk, ChunkStrategy
from app.rag.rerank.apply import rerank_hits
from app.rag.rerank.fake import FakeReranker
from app.rag.rerank.models import RerankError
from app.rag.vectorstore.models import SearchHit


def _make_hit(chunk_id: str, text: str, score: float = 0.5) -> SearchHit:
    chunk = Chunk(
        id=chunk_id,
        strategy=ChunkStrategy.STRUCTURE,
        source_file="doc1.pdf",
        chunk_index=0,
        text=text,
        page_start=1,
        page_end=1,
        char_start=0,
        char_end=len(text),
        token_count=len(text.split()),
    )
    return SearchHit(chunk=chunk, score=score, source="hybrid")


def test_rerank_hits_successful_reordering():
    h0 = _make_hit("c0", "kötü içerik", score=0.99)
    h1 = _make_hit("c1", "harika aranan iade bilgisi", score=0.60)
    h2 = _make_hit("c2", "orta seviye bilgi", score=0.75)

    reranker = FakeReranker(scores=[0.1, 0.95, 0.5])
    reordered, status, results = rerank_hits(
        "iade bilgisi", [h0, h1, h2], reranker, top_k=2, fail_open=True
    )

    assert status == "ok"
    assert len(reordered) == 2
    # h1 (0.95), h2 (0.50)
    assert reordered[0].chunk.id == "c1"
    assert reordered[1].chunk.id == "c2"

    # Orijinal SearchHit skor ve kaynak bilgisi değişmemiş olmalı
    assert reordered[0].score == 0.60
    assert reordered[0].source == "hybrid"
    assert reordered[1].score == 0.75

    # RerankResults doğrulaması
    assert len(results) == 3
    assert results[0].index == 1
    assert results[0].score == 0.95


def test_rerank_hits_empty():
    reranker = FakeReranker()
    reordered, status, results = rerank_hits(
        "soru", [], reranker, top_k=5, fail_open=True
    )
    assert reordered == []
    assert status == "ok"
    assert results == []


def test_rerank_hits_top_k_larger_than_hits():
    h0 = _make_hit("c0", "bilgi 0")
    h1 = _make_hit("c1", "bilgi 1")
    reranker = FakeReranker(scores=[0.2, 0.8])

    reordered, status, _ = rerank_hits("soru", [h0, h1], reranker, top_k=10, fail_open=True)
    assert len(reordered) == 2
    assert reordered[0].chunk.id == "c1"
    assert reordered[1].chunk.id == "c0"


def test_rerank_hits_fail_open_on_rerank_error(caplog):
    h0 = _make_hit("c0", "gizli doküman metni 0")
    h1 = _make_hit("c1", "gizli doküman metni 1")
    reranker = FakeReranker(raise_on_call=RerankError("bağlantı koptu"))

    with caplog.at_level(logging.WARNING):
        reordered, status, results = rerank_hits(
            "hassas_kullanici_sorusu", [h0, h1], reranker, top_k=1, fail_open=True
        )

    assert status == "failed"
    assert len(reordered) == 1
    # Orijinal sıra korunur: c0 ilk sırada
    assert reordered[0].chunk.id == "c0"
    assert results == []

    # Loglarda soru ve doküman metni sızmamalı
    log_text = caplog.text
    assert "fail-open devrede" in log_text
    assert "hassas_kullanici_sorusu" not in log_text
    assert "gizli doküman metni" not in log_text


def test_rerank_hits_fail_closed_on_rerank_error():
    h0 = _make_hit("c0", "içerik")
    reranker = FakeReranker(raise_on_call=RerankError("hata oluştu"))

    with pytest.raises(RerankError, match="hata oluştu"):
        rerank_hits("soru", [h0], reranker, top_k=1, fail_open=False)


def test_rerank_hits_fail_open_on_unexpected_exception(caplog):
    class BuggyReranker:
        model_id = "buggy"

        def rerank(self, query, docs):
            raise KeyError("beklenmeyen anahtar")

    h0 = _make_hit("c0", "içerik")
    reranker = BuggyReranker()

    with caplog.at_level(logging.ERROR):
        reordered, status, _ = rerank_hits(
            "soru", [h0], reranker, top_k=1, fail_open=True  # type: ignore[arg-type]
        )

    assert status == "failed"
    assert reordered[0].chunk.id == "c0"
    assert "beklenmeyen hata oluştu" in caplog.text
