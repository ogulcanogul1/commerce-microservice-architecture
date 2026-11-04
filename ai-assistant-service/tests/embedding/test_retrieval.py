import numpy as np
import pytest

from app.rag.chunking.models import Chunk, ChunkStrategy
from app.rag.chunking.tokenizer import WhitespaceTokenizer
from app.rag.embedding.fake import FakeEmbedder
from app.rag.evaluation.chunking.retrieval import BM25Retriever, Retriever
from app.rag.evaluation.embedding.retrieval import DenseRetriever, HybridRetriever


def create_sample_chunks() -> list[Chunk]:
    return [
        Chunk(
            id="c0",
            strategy=ChunkStrategy.STRUCTURE,
            source_file="kargo.pdf",
            chunk_index=0,
            text="Kargo teslimat suresi standart 24 saattir.",
            heading_path=["Teslimat"],
            breadcrumb="Teslimat",
            token_count=6,
            page_start=1,
            page_end=1,
            char_start=0,
            char_end=42,
        ),
        Chunk(
            id="c1",
            strategy=ChunkStrategy.STRUCTURE,
            source_file="iade.pdf",
            chunk_index=1,
            text="Iade ve degisim kosullari 14 gun gecerlidir.",
            heading_path=["Iade"],
            breadcrumb="Iade",
            token_count=7,
            page_start=1,
            page_end=1,
            char_start=0,
            char_end=45,
        ),
        Chunk(
            id="c2",
            strategy=ChunkStrategy.STRUCTURE,
            source_file="garanti.pdf",
            chunk_index=2,
            text="Elektronik urunlerde garanti suresi 2 yildir.",
            heading_path=["Garanti"],
            breadcrumb="Garanti",
            token_count=6,
            page_start=1,
            page_end=1,
            char_start=0,
            char_end=46,
        ),
    ]


def test_retrievers_satisfy_protocol():
    embedder = FakeEmbedder()
    dense = DenseRetriever(embedder)
    bm25 = BM25Retriever()
    hybrid = HybridRetriever(dense, bm25)

    assert isinstance(dense, Retriever)
    assert isinstance(hybrid, Retriever)


def test_dense_retriever_hit_at_1():
    embedder = FakeEmbedder()
    retriever = DenseRetriever(embedder)
    chunks = create_sample_chunks()
    retriever.index(chunks)

    # c1 (iade) ile ilgili sorgu
    results = retriever.search("iade degisim kosullari", k=3)
    assert len(results) == 3
    assert results[0].id == "c1"


def test_dense_retriever_empty_index_and_empty_query():
    embedder = FakeEmbedder()
    retriever = DenseRetriever(embedder)

    # İndekslenmemiş arama
    assert retriever.search("herhangi bir sorgu") == []

    chunks = create_sample_chunks()
    retriever.index(chunks)

    # Boş sorgu
    assert retriever.search("") == []
    assert retriever.search("   ") == []


def test_dense_retriever_k_greater_than_n():
    embedder = FakeEmbedder()
    retriever = DenseRetriever(embedder)
    chunks = create_sample_chunks()
    retriever.index(chunks)

    # 3 chunk var ama k=10 istiyoruz
    results = retriever.search("kargo teslimat", k=10)
    assert len(results) == 3


def test_dense_search_by_budget():
    embedder = FakeEmbedder()
    retriever = DenseRetriever(embedder)
    chunks = create_sample_chunks()
    retriever.index(chunks)

    tokenizer = WhitespaceTokenizer()
    # c0 (6 token), c1 (7 token), c2 (6 token). Bütçe: 10 token -> Sadece ilk chunk (6 <= 10) sığmalı
    results = retriever.search_by_budget("kargo teslimat", budget=10, tokenizer=tokenizer)
    assert len(results) == 1
    assert results[0].id == "c0"


def test_hybrid_retriever_rrf_top_rank():
    embedder = FakeEmbedder()
    dense = DenseRetriever(embedder)
    bm25 = BM25Retriever()
    hybrid = HybridRetriever(dense, bm25, k_rrf=60)

    chunks = create_sample_chunks()
    hybrid.index(chunks)

    # Hem dense hem bm25 için güçlü kelimeler içeren sorgu
    results = hybrid.search("kargo teslimat suresi", k=3)
    assert len(results) == 3
    # Her iki sıralamada da üstte olan c0, RRF ile 1. sırada çıkmalı
    assert results[0].id == "c0"


def test_hybrid_search_by_budget():
    embedder = FakeEmbedder()
    dense = DenseRetriever(embedder)
    bm25 = BM25Retriever()
    hybrid = HybridRetriever(dense, bm25, k_rrf=60)

    chunks = create_sample_chunks()
    hybrid.index(chunks)

    tokenizer = WhitespaceTokenizer()
    # Bütçe: 15 token. c0 (6) + c2 veya c1 -> max 2 chunk
    results = hybrid.search_by_budget("garanti suresi", budget=15, tokenizer=tokenizer)
    assert len(results) <= 2
    total_tokens = sum(tokenizer.count(c.text) for c in results)
    assert total_tokens <= 15


def test_hybrid_retriever_custom_weights():
    embedder = FakeEmbedder()
    dense = DenseRetriever(embedder)
    bm25 = BM25Retriever()

    # Dense %80, BM25 otomatik olarak %20 (1.0 - 0.8)
    hybrid = HybridRetriever(
        dense,
        bm25,
        dense_weight=0.8,
    )
    assert hybrid.dense_weight == 0.8
    assert np.isclose(hybrid.bm25_weight, 0.2)

    chunks = create_sample_chunks()
    hybrid.index(chunks)

    res = hybrid.search("iade kosullari", k=3)
    assert len(res) == 3
    assert res[0].id == "c1"

    # [0.0, 1.0] aralığı dışındaki ağırlıklar hata fırlatmalı
    with pytest.raises(ValueError, match="between 0.0 and 1.0"):
        HybridRetriever(dense, bm25, dense_weight=-0.1)

    with pytest.raises(ValueError, match="between 0.0 and 1.0"):
        HybridRetriever(dense, bm25, dense_weight=1.5)


