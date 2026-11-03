import pytest
from app.rag.chunking.models import Chunk, ChunkStrategy
from app.rag.chunking.tokenizer import WhitespaceTokenizer
from app.rag.evaluation.chunking.dataset import GoldenQuestion
from app.rag.evaluation.chunking.retrieval import (
    BM25Retriever,
    Retriever,
    chunk_contains_evidence,
    evaluate_retrieval,
)


def test_retriever_protocol_conformance():
    bm25 = BM25Retriever()
    assert isinstance(bm25, Retriever)


def test_chunk_contains_evidence_helper():
    chunk = Chunk(
        id="c1",
        strategy=ChunkStrategy.STRUCTURE,
        source_file="d.pdf",
        chunk_index=0,
        text="Kozmetik ürünler ambalajı açılınca iade alınamaz. Hijyen kuralıdır.",
        token_count=10,
        page_start=1,
        page_end=1,
        char_start=0,
        char_end=65,
    )

    # Tam eşleşme (büyük/küçük harf toleranslı)
    assert chunk_contains_evidence(chunk, ["kozmetik ürünler ambalajı açılınca"]) is True
    # Çoklu parça
    assert chunk_contains_evidence(chunk, ["Kozmetik", "iade alınamaz", "Hijyen"]) is True
    # Olmayan parça
    assert chunk_contains_evidence(chunk, ["Buzdolabı"]) is False


def test_bm25_search_and_metrics_calculation():
    # 3 chunk'lı sahte korpus
    chunks = [
        Chunk(
            id="c0",
            strategy=ChunkStrategy.STRUCTURE,
            source_file="doc.pdf",
            chunk_index=0,
            text="Genel teslimat süresi 24 saattir. Siparişler hızla kargoya verilir.",
            token_count=10,
            page_start=1,
            page_end=1,
            char_start=0,
            char_end=65,
        ),
        Chunk(
            id="c1",
            strategy=ChunkStrategy.STRUCTURE,
            source_file="doc.pdf",
            chunk_index=1,
            text="Kozmetik ürünlerde ambalaj açıldıysa hijyen nedeniyle iade yapılmaz.",
            token_count=10,
            page_start=1,
            page_end=1,
            char_start=66,
            char_end=135,
        ),
        Chunk(
            id="c2",
            strategy=ChunkStrategy.STRUCTURE,
            source_file="doc.pdf",
            chunk_index=2,
            text="Beyaz eşyalarda garanti 3 yıldır. Kurulum servisle yapılmalıdır.",
            token_count=10,
            page_start=2,
            page_end=2,
            char_start=136,
            char_end=200,
        ),
    ]

    questions = [
        # 1. Soru: c1 ile tam eşleşir, 1. sırada gelmeli -> Hit@1 = True, MRR = 1.0
        GoldenQuestion(
            id="Q1",
            question="Açılmış kozmetik ürün iade edilebilir mi?",
            doc="doc.pdf",
            evidence=["Kozmetik ürünlerde ambalaj açıldıysa hijyen nedeniyle iade yapılmaz."],
            category="exception",
        ),
        # 2. Soru: c2 ile eşleşir -> Hit@1 = True, MRR = 1.0
        GoldenQuestion(
            id="Q2",
            question="Beyaz eşya garanti süresi kaç yıl?",
            doc="doc.pdf",
            evidence=["Beyaz eşyalarda garanti 3 yıldır."],
            category="single_fact",
        ),
        # 3. Soru: Kanıt korpusun hiçbir chunk'ında tek parça yok -> Intact = False, Fragmented = True
        GoldenQuestion(
            id="Q3",
            question="Televizyon kurulumu kuralı nedir?",
            doc="doc.pdf",
            evidence=["Televizyon panelleri evde servis tarafından takılır."],
            category="table_lookup",
        ),
    ]

    retriever = BM25Retriever()
    summary, results = evaluate_retrieval(retriever, questions, chunks)

    assert summary.total_questions == 3
    # Q1 ve Q2 intact (2/3 = 0.6667), Q3 fragmented (1/3 = 0.3333)
    assert summary.evidence_intact_ratio == round(2 / 3, 4)
    assert summary.evidence_fragmented_ratio == round(1 / 3, 4)

    # Q1 ve Q2 1. sırada bulundu, Q3 bulunamadı -> Hit@1 = 2/3 = 0.6667
    assert summary.hit_at_1 == round(2 / 3, 4)
    assert summary.hit_at_3 == round(2 / 3, 4)
    # MRR = (1.0 + 1.0 + 0.0) / 3 = 0.6667
    assert summary.mrr == round(2 / 3, 4)

    # Kategori kırılımı
    assert summary.category_hit3["exception"] == 1.0
    assert summary.category_hit3["single_fact"] == 1.0
    assert summary.category_hit3["table_lookup"] == 0.0


def test_bm25_search_by_token_budget():
    tokenizer = WhitespaceTokenizer()
    chunks = [
        Chunk(
            id="c0",
            strategy=ChunkStrategy.FIXED,
            source_file="d.pdf",
            chunk_index=0,
            text="kargo teslimat süresi hızlıdır.",
            token_count=4,
            page_start=1,
            page_end=1,
            char_start=0,
            char_end=30,
        ),
        Chunk(
            id="c1",
            strategy=ChunkStrategy.FIXED,
            source_file="d.pdf",
            chunk_index=1,
            text="kargo adresi değiştirilebilir.",
            token_count=3,
            page_start=1,
            page_end=1,
            char_start=31,
            char_end=60,
        ),
        Chunk(
            id="c2",
            strategy=ChunkStrategy.FIXED,
            source_file="d.pdf",
            chunk_index=2,
            text="kargo takip numarası SMS ile iletilir.",
            token_count=6,
            page_start=1,
            page_end=1,
            char_start=61,
            char_end=100,
        ),
    ]

    retriever = BM25Retriever()
    retriever.index(chunks)

    # Bütçe: 8 token. İlk 2 chunk (4 + 3 = 7 token <= 8) sığar, 3. chunk sığmaz
    selected = retriever.search_by_budget("kargo", budget=8, tokenizer=tokenizer)
    assert len(selected) == 2
    total_tokens = sum(tokenizer.count(c.text) for c in selected)
    assert total_tokens <= 8
