from pathlib import Path
import pytest

from app.rag.chunking.models import Chunk
from app.rag.chunking.tokenizer import TiktokenTokenizer
from app.rag.embedding.cache import DiskEmbeddingCache
from app.rag.embedding.models import EmbeddingConfig, EmbeddingProvider
from app.rag.evaluation.chunking.dataset import GoldenQuestion
from app.rag.evaluation.chunking.retrieval import BM25Retriever, RetrievalEvalSummary
from app.rag.evaluation.embedding.compare import (
    evaluate_single_model,
    generate_markdown_report,
    parse_model_string,
)


def test_parse_model_string():
    cfg1 = parse_model_string("openai/text-embedding-3-small")
    assert cfg1.provider == EmbeddingProvider.OPENAI
    assert cfg1.model == "text-embedding-3-small"
    assert cfg1.dimensions is None

    cfg2 = parse_model_string("openai/text-embedding-3-small@512")
    assert cfg2.provider == EmbeddingProvider.OPENAI
    assert cfg2.dimensions == 512

    cfg3 = parse_model_string("gemini/text-embedding-004")
    assert cfg3.provider == EmbeddingProvider.GEMINI
    assert cfg3.model == "text-embedding-004"

    cfg_fake = parse_model_string("fake")
    assert cfg_fake.provider == EmbeddingProvider.FAKE


def test_generate_markdown_report_formatting():
    bm25_summary = RetrievalEvalSummary(
        total_questions=10,
        evidence_intact_ratio=1.0,
        evidence_fragmented_ratio=0.0,
        hit_at_1=0.8,
        hit_at_3=0.9,
        hit_at_5=1.0,
        mrr=0.85,
        category_hit3={"single_fact": 1.0, "exception": 0.8},
    )

    results = [
        {
            "model_id": "test/model",
            "provider": "fake",
            "model": "model",
            "dimensions": 128,
            "embed_duration_sec": 0.12,
            "avg_query_sec": 0.005,
            "est_cost_usd": 0.0,
            "storage_kb": 4.5,
            "doc_cache_hits": 5,
            "doc_cache_misses": 5,
            "query_cache_hits": 10,
            "query_cache_misses": 0,
            "token_divergence_ratio": 1.05,
            "all_chunks_fit": True,
            "max_chunk_tokens": 120,
            "dense_summary": bm25_summary.model_dump(),
            "hybrid_summary": bm25_summary.model_dump(),
        }
    ]

    report = generate_markdown_report(
        results=results,
        bm25_summary=bm25_summary,
        git_hash="abc1234",
        doc_count=1,
        chunk_count=5,
        question_count=10,
    )

    assert "# 📊 Embedding Model Karşılaştırma" in report
    assert "BM25 (Baseline)" in report
    assert "test/model" in report
    assert "single_fact" in report


def test_evaluate_single_model_real_run(tmp_path):
    # Gerçek evaluate_single_model akışını fake embedder ile uçtan uca çalıştır
    chunks = [
        Chunk(
            id="c1",
            source_file="test.pdf",
            chunk_index=0,
            page_start=1,
            page_end=1,
            text="Siparis teslimat kargo takip suresi 3 gundur.",
            token_count=10,
            char_start=0,
            char_end=45,
            strategy="fixed",
        ),
        Chunk(
            id="c2",
            source_file="test.pdf",
            chunk_index=1,
            page_start=1,
            page_end=1,
            text="Iade ve degisim sartlari 14 gun icindedir.",
            token_count=10,
            char_start=46,
            char_end=90,
            strategy="fixed",
        ),
    ]

    questions = [
        GoldenQuestion(
            id="Q01",
            question="Kargo teslimat suresi kac gun?",
            doc="test.pdf",
            evidence=["Siparis teslimat kargo takip suresi 3 gundur."],
            category="single_fact",
        ),
    ]

    bm25 = BM25Retriever()
    bm25.index(chunks)

    cache = DiskEmbeddingCache(tmp_path / "test_eval.db")
    tokenizer = TiktokenTokenizer()

    cfg = EmbeddingConfig(
        provider=EmbeddingProvider.FAKE,
        model="deterministic-bow",
        dimensions=128,
    )

    res = evaluate_single_model(
        config=cfg,
        all_chunks=chunks,
        questions=questions,
        bm25_retriever=bm25,
        cache=cache,
        tokenizer=tokenizer,
        dense_weight=0.5,
    )

    assert res["model_id"] == "fake/deterministic-bow@128"
    assert res["dimensions"] == 128
    assert res["all_chunks_fit"] is True
    assert res["token_divergence_ratio"] is not None
    assert isinstance(res["token_divergence_ratio"], float)
    assert res["token_divergence_ratio"] > 0.0
    assert "hit_at_1" in res["dense_summary"]
    assert "hit_at_1" in res["hybrid_summary"]
    assert res["doc_cache_misses"] == 2
    assert res["doc_cache_hits"] == 0
