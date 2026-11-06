"""Parite değerlendirme (parity.py) runner'ı için birim testleri."""

from pathlib import Path
from qdrant_client import QdrantClient

from app.rag.chunking.models import Chunk, ChunkStrategy
from app.rag.embedding.fake import FakeEmbedder
from app.rag.evaluation.chunking.dataset import GoldenQuestion
from app.rag.evaluation.qdrant.parity import run_parity_evaluation


def _make_sample_data():
    """Parite testi için sentetik chunk ve soru setleri üretir."""
    chunks = [
        Chunk(
            id="c1",
            strategy=ChunkStrategy.STRUCTURE,
            source_file="sozlesme.pdf",
            chunk_index=0,
            text="Cayma hakkı süresi 14 gündür. Tüketici herhangi bir gerekçe göstermeksizin iade edebilir.",
            page_start=1,
            page_end=1,
            char_start=0,
            char_end=90,
            token_count=15,
        ),
        Chunk(
            id="c2",
            strategy=ChunkStrategy.STRUCTURE,
            source_file="kargo.pdf",
            chunk_index=0,
            text="Standart kargo teslimat süresi 2 ile 4 iş günüdür. Kargo takip numarası SMS ile iletilir.",
            page_start=1,
            page_end=1,
            char_start=0,
            char_end=95,
            token_count=16,
        ),
        Chunk(
            id="c3",
            strategy=ChunkStrategy.STRUCTURE,
            source_file="garanti.pdf",
            chunk_index=0,
            text="Yetkili servis garanti süresi 2 yıldır. Kullanıcı hataları garanti kapsamı dışındadır.",
            page_start=1,
            page_end=1,
            char_start=0,
            char_end=90,
            token_count=14,
        ),
    ]

    questions = [
        GoldenQuestion(
            id="Q01",
            question="Cayma hakkı süresi kaç gündür?",
            doc="sozlesme.pdf",
            evidence=["14 gündür"],
            category="single_fact",
        ),
        GoldenQuestion(
            id="Q02",
            question="Kargo teslimatı ne kadar sürer?",
            doc="kargo.pdf",
            evidence=["2 ile 4 iş günüdür"],
            category="single_fact",
        ),
        GoldenQuestion(
            id="Q03",
            question="Garanti süresi kaç yıldır?",
            doc="garanti.pdf",
            evidence=["2 yıldır"],
            category="single_fact",
        ),
    ]
    return chunks, questions


def test_parity_runner_end_to_end_and_dense_diff_zero(tmp_path):
    """Parite değerlendirme runner'ı uçtan uca çalışmalı, dense farkı 0 olmalı ve rapor dosyaları üretilmelidir."""
    chunks, questions = _make_sample_data()
    embedder = FakeEmbedder(dimensions=32, model_id="fake/parity-test")
    client = QdrantClient(":memory:")

    report = run_parity_evaluation(
        embedder=embedder,
        questions=questions,
        all_chunks=chunks,
        client=client,
        reports_dir=tmp_path,
    )

    # 1. Kriter Kontrolleri
    crit = report["criteria"]
    # Dense arama farkı kesinlikle 0 olmalıdır
    assert crit["dense_ranking_diffs"] == 0
    assert crit["dense_passed"] is True

    # Hybrid arama kabul sınırlarında olmalıdır
    assert crit["hybrid_passed"] is True
    assert crit["all_passed"] is True

    # 2. Dosya Kontrolleri
    files = report["report_files"]
    md_file = Path(files["markdown"])
    json_file = Path(files["json"])

    assert md_file.exists()
    assert json_file.exists()

    md_content = md_file.read_text(encoding="utf-8")
    assert "Qdrant vs Bellek İçi Parite Değerlendirme Raporu" in md_content
    assert "BAŞARILI (PARITY ACHIEVED)" in md_content
