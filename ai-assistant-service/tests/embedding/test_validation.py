from pathlib import Path
import pytest

from app.rag.chunking import DefaultChunker
from app.rag.chunking.models import Chunk, ChunkStrategy, ChunkingConfig
from app.rag.chunking.tokenizer import TiktokenTokenizer, WhitespaceTokenizer
from app.rag.embedding.fake import FakeEmbedder
from app.rag.embedding.models import EmbeddingConfig, EmbeddingProvider
from app.rag.embedding.providers.gemini_embedder import GeminiEmbedder
from app.rag.embedding.providers.local_embedder import LocalEmbedder
from app.rag.embedding.providers.openai_embedder import OpenAIEmbedder
from app.rag.evaluation.embedding.validation import (
    compute_token_divergence_ratio,
    validate_chunks_fit,
)
from app.rag.ingestion.pdf.loader import PDFLoader


def test_validate_chunks_fit_synthetic():
    tok = WhitespaceTokenizer()
    chunks = [
        Chunk(
            id="c_small",
            strategy=ChunkStrategy.STRUCTURE,
            source_file="d.pdf",
            chunk_index=0,
            text="kisa bir metin parçasıdır",
            token_count=4,
            page_start=1,
            page_end=1,
            char_start=0,
            char_end=25,
        ),
        Chunk(
            id="c_big",
            strategy=ChunkStrategy.STRUCTURE,
            source_file="d.pdf",
            chunk_index=1,
            text="bu metin cok daha uzun bir metindir ve limiti asacaktir kesinlikle",
            token_count=10,
            page_start=1,
            page_end=1,
            char_start=26,
            char_end=90,
        ),
    ]

    # Max 5 token sınırı olan embedder
    embedder_small = FakeEmbedder(max_input_tokens=5)
    report = validate_chunks_fit(chunks, embedder_small, tokenizer=tok)

    assert report.total_chunks == 2
    assert report.all_fit is False
    assert len(report.oversized_chunks) == 1
    assert report.oversized_chunks[0][0] == "c_big"

    # Max 20 token sınırı olan embedder
    embedder_generous = FakeEmbedder(max_input_tokens=20)
    report_gen = validate_chunks_fit(chunks, embedder_generous, tokenizer=tok)
    assert report_gen.all_fit is True
    assert len(report_gen.oversized_chunks) == 0


def test_compute_token_divergence_ratio():
    texts = ["merhaba dunya", "turkiye e-ticaret lojistik"]
    w_tok = WhitespaceTokenizer()
    t_tok = TiktokenTokenizer()

    ratio = compute_token_divergence_ratio(texts, w_tok, t_tok)
    assert isinstance(ratio, float)
    assert ratio > 0.0

    # Boş metin
    assert compute_token_divergence_ratio([], w_tok, t_tok) == 1.0


def test_golden_set_corpus_fits_all_candidate_models():
    """Verify that DefaultChunker output on the golden set corpus fits all candidate models."""
    docs_dir = Path("eval/chunking/docs")
    if not docs_dir.exists():
        pytest.skip(f"{docs_dir} not found; skipping corpus fit test.")

    pdf_files = sorted(docs_dir.glob("*.pdf"))
    if not pdf_files:
        pytest.skip("No PDF files found in eval/chunking/docs.")

    loader = PDFLoader()
    documents = [loader.load(p) for p in pdf_files]

    tokenizer = TiktokenTokenizer()
    chunker = DefaultChunker(tokenizer=tokenizer, config=ChunkingConfig())

    all_chunks = []
    for doc in documents:
        all_chunks.extend(chunker.chunk(doc))

    assert len(all_chunks) > 0

    # Aday modeller ve sınırları:
    # 1. OpenAI Small (8191)
    openai_small = OpenAIEmbedder(
        EmbeddingConfig(provider=EmbeddingProvider.OPENAI, model="text-embedding-3-small"),
        api_key="mock",
    )
    # 2. Gemini (2048)
    gemini = GeminiEmbedder(
        EmbeddingConfig(provider=EmbeddingProvider.GEMINI, model="text-embedding-004"),
        api_key="mock",
    )
    # 3. Local E5-Small (512 - En dar limitli adayımız!)
    local_e5 = LocalEmbedder(
        EmbeddingConfig(provider=EmbeddingProvider.LOCAL, model="multilingual-e5-small"),
    )
    # 4. Local BGE-M3 (8192)
    local_bge = LocalEmbedder(
        EmbeddingConfig(provider=EmbeddingProvider.LOCAL, model="bge-m3"),
    )

    candidates = [openai_small, gemini, local_e5, local_bge]

    for model in candidates:
        report = validate_chunks_fit(all_chunks, model, tokenizer=tokenizer)
        assert (
            report.all_fit
        ), f"Model {model.model_id} exceeded token limit! Oversized chunks: {report.oversized_chunks}"
        assert report.max_chunk_tokens <= model.max_input_tokens
