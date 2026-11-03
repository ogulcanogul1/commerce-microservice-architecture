from pathlib import Path
import pytest
from app.rag.chunking.models import ChunkingConfig, ChunkStrategy
from app.rag.chunking.tokenizer import WhitespaceTokenizer
from app.rag.evaluation.chunking.compare import (
    format_markdown_report,
    run_single_experiment,
)
from app.rag.evaluation.chunking.dataset import GoldenQuestion
from app.rag.ingestion.models import Element, ElementType, ParsedDocument, QualityReport


def test_run_single_experiment_and_format_markdown():
    doc = ParsedDocument(
        source_file="d.pdf",
        elements=[
            Element(
                type=ElementType.HEADING,
                text="Genel Başlık",
                page_start=1,
                page_end=1,
            ),
            Element(
                type=ElementType.PARAGRAPH,
                text="İade süresi 14 gündür. Anlaşmalı kargo firmasıyla gönderilmelidir.",
                page_start=1,
                page_end=1,
                heading_path=["Genel Başlık"],
            ),
        ],
        quality=QualityReport(page_count=1, status="ok"),
        parser_name="mock",
        parser_version="1.0",
    )

    questions = [
        GoldenQuestion(
            id="Q1",
            question="İade süresi kaç gün?",
            doc="d.pdf",
            evidence=["İade süresi 14 gündür."],
            category="single_fact",
        )
    ]

    tokenizer = WhitespaceTokenizer()
    config = ChunkingConfig(max_tokens=40, overlap_tokens=10, min_tokens=10)

    res = run_single_experiment(
        strategy=ChunkStrategy.STRUCTURE,
        config=config,
        documents=[doc],
        questions=questions,
        tokenizer=tokenizer,
    )

    assert res["strategy"] == "structure"
    assert res["chunk_count"] > 0
    assert res["evidence_intact_ratio"] == 1.0
    assert res["hit_at_1"] == 1.0
    assert "single_fact" in res["category_hit3"]

    # Markdown formatlama testi
    md = format_markdown_report(
        experiments=[res],
        git_hash="test_hash",
        doc_count=1,
        question_count=1,
    )

    assert "Ana Karşılaştırma Matrisi" in md
    assert "Kategori Bazlı Hit@3 Kırılım Matrisi" in md
    assert "test_hash" in md
    assert "structure" in md
