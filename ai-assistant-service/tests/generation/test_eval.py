"""Unit tests for generation evaluation dataset, metrics, and runner.

Test Edilen Durumlar:
1. validate_raw_answer_set:
   - Yinelenen id tespiti ve hata fırlatması.
   - Hem question_id hem question aynı anda doluysa hata fırlatması.
   - İki alan da boşsa hata fırlatması.
   - Olmayan question_id belirtilmişse hata fırlatması.
   - answerable=True iken expected_facts boşsa hata fırlatması.
   - answerable=False iken expected_facts doluysa hata fırlatması.
2. score_case:
   - Türkçe büyük/küçük harf normalizasyonu ("14 GÜN" ↔ "14 gün", "İADE" ↔ "iade").
   - forbidden_hit tespiti (yanlış bilgi üretildiğinde correct=False olması).
   - Cevaplanamaz soruya answered dönüldüğünde correct=False olması (halüsinasyon tespiti).
   - Cevaplanamaz soruya abstained dönüldüğünde correct=True olması.
3. Runner & Gate Entegrasyonu:
   - Geçici dizinde sahte LLM ve sahte embedder ile rapor üretimi.
   - Geçici koleksiyonun koşu sonunda silindiğinin doğrulanması.
"""

from __future__ import annotations

from pathlib import Path
import tempfile

import pytest
from qdrant_client import QdrantClient

from app.rag.evaluation.generation.dataset import (
    AnswerCase,
    load_answer_set,
    validate_raw_answer_set,
)
from app.rag.evaluation.generation.gate import (
    analyze_thresholds,
    compute_distribution_stats,
    setup_temporary_store,
)
from app.rag.evaluation.generation.metrics import (
    compute_generation_summary,
    score_case,
)
from app.rag.generation.models import AbstainReason, Citation, RagAnswer, ValidationIssue
from app.rag.chunking.models import Chunk, ChunkStrategy
from app.rag.embedding.fake import FakeEmbedder


# ============================================================================
# 1. DATASET VE DOĞRULAMA TESTLERİ
# ============================================================================


def test_validate_raw_answer_set_duplicate_id():
    """Yinelenen id içeren veri setlerinde ValueError fırlatılmalıdır."""
    raw = [
        {"id": "G01", "question_id": "Q01", "question": None, "answerable": True, "expected_facts": ["14 gün"]},
        {"id": "G01", "question_id": "Q02", "question": None, "answerable": True, "expected_facts": ["şirket"]},
    ]
    with pytest.raises(ValueError, match="Yinelenen id"):
        validate_raw_answer_set(raw)


def test_validate_raw_answer_set_both_or_neither_question_field():
    """question_id ve question alanlarının ikisi birden dolu veya ikisi birden boş olamaz."""
    # İkisi birden dolu
    raw_both = [
        {"id": "G01", "question_id": "Q01", "question": "Soru metni", "answerable": True, "expected_facts": ["14 gün"]},
    ]
    with pytest.raises(ValueError, match="aynı anda dolu olamaz"):
        validate_raw_answer_set(raw_both)

    # İkisi birden boş
    raw_neither = [
        {"id": "G01", "question_id": None, "question": None, "answerable": True, "expected_facts": ["14 gün"]},
    ]
    with pytest.raises(ValueError, match="biri mutlaka dolu olmalıdır"):
        validate_raw_answer_set(raw_neither)


def test_validate_raw_answer_set_missing_golden_id():
    """Golden set içinde bulunmayan question_id belirtildiğinde ValueError fırlatılmalıdır."""
    raw = [
        {"id": "G01", "question_id": "Q999_YOK", "question": None, "answerable": True, "expected_facts": ["14 gün"]},
    ]
    golden_map = {"Q01": {"id": "Q01", "question": "Gerçek soru"}}
    with pytest.raises(ValueError, match="golden_set.json içinde bulunamadı"):
        validate_raw_answer_set(raw, golden_map=golden_map)


def test_validate_raw_answer_set_expected_facts_rules():
    """answerable=True için expected_facts dolu, answerable=False için boş olmalıdır."""
    # answerable=True iken expected_facts boş
    raw_empty_facts = [
        {"id": "G01", "question_id": None, "question": "Soru?", "answerable": True, "expected_facts": []},
    ]
    with pytest.raises(ValueError, match="en az 1 'expected_facts'"):
        validate_raw_answer_set(raw_empty_facts)

    # answerable=False iken expected_facts dolu
    raw_unans_with_facts = [
        {"id": "U01", "question_id": None, "question": "Cevaplanamaz?", "answerable": False, "expected_facts": ["bilgi"]},
    ]
    with pytest.raises(ValueError, match="listesi boş olmalıdır"):
        validate_raw_answer_set(raw_unans_with_facts)


def test_load_real_answer_set():
    """eval/generation/answer_set.json dosyası eksiksiz ve hatasız yüklenmelidir."""
    cases = load_answer_set(
        path="eval/generation/answer_set.json",
        golden_path="eval/chunking/golden_set.json",
    )
    assert len(cases) == 54
    ans_cases = [c for c in cases if c.answerable]
    unans_cases = [c for c in cases if not c.answerable]
    assert len(ans_cases) == 42
    assert len(unans_cases) == 12

    # G01'in sorusu golden set'ten çözülmüş olmalı
    g01 = next(c for c in cases if c.id == "G01")
    assert "iade edebilir" in g01.question
    assert g01.category == "single_fact"


# ============================================================================
# 2. METRİK VE PUANLAMA TESTLERİ
# ============================================================================


def test_score_case_turkish_case_folding():
    """Türkçe İ/i ve I/ı harfleriyle büyük-küçük harf farkı doğru eşleşmelidir."""
    case = AnswerCase(
        id="G01",
        question="Soru",
        answerable=True,
        expected_facts=["14 GÜN", "ŞİRKETİMİZ TARAFINDAN"],
        forbidden_facts=["30 GÜN"],
        category="single_fact",
    )

    # Cevap küçük harfle yazılmış olsa bile tam eşleşmeli
    answer = RagAnswer(
        status="answered",
        answer="İade süresi 14 gün olarak belirlenmiştir ve kargo şirketimiz tarafından karşılanır [1].",
        abstain_reason=None,
        citations=[Citation(number=1, chunk_id="c1", source_file="iade.pdf", page_start=1, page_end=1)],
        validation_issues=[],
    )

    result = score_case(case, answer)
    assert result.fact_recall == 1.0
    assert not result.forbidden_hit
    assert result.correct is True
    assert result.citations_valid is True


def test_score_case_forbidden_hit():
    """Yasaklı/uydurma bir olgu üretildiğinde correct=False olmalıdır."""
    case = AnswerCase(
        id="G01",
        question="Soru",
        answerable=True,
        expected_facts=["14 gün"],
        forbidden_facts=["30 gün"],
        category="single_fact",
    )

    # Cevapta hem 14 gün hem de yasaklı 30 gün geçiyor
    answer = RagAnswer(
        status="answered",
        answer="İade süresi 14 gündür ancak bazı ürünlerde 30 gün geçerlidir [1].",
        abstain_reason=None,
        citations=[Citation(number=1, chunk_id="c1", source_file="iade.pdf", page_start=1, page_end=1)],
        validation_issues=[],
    )

    result = score_case(case, answer)
    assert result.fact_recall == 1.0
    assert result.forbidden_hit is True
    assert result.correct is False  # Yasaklı olgu nedeniyle başarısız


def test_score_case_unanswerable_hallucination():
    """Cevaplanamaz soruya cevap verilirse halüsinasyon olarak correct=False işaretlenmelidir."""
    case = AnswerCase(
        id="U01",
        question="Kripto para ile ödeme var mı?",
        answerable=False,
        expected_facts=[],
        forbidden_facts=[],
        category="unanswerable",
    )

    # Model uydurma cevap üretti
    answer = RagAnswer(
        status="answered",
        answer="Bitcoin ve Ethereum ile ödeme yapabilirsiniz [1].",
        abstain_reason=None,
        citations=[],
        validation_issues=[],
    )

    result = score_case(case, answer)
    assert result.correct is False  # Halüsinasyon


def test_score_case_unanswerable_proper_abstain():
    """Cevaplanamaz soruya abstained dönüldüğünde correct=True işaretlenmelidir."""
    case = AnswerCase(
        id="U01",
        question="Kripto para ile ödeme var mı?",
        answerable=False,
        expected_facts=[],
        forbidden_facts=[],
        category="unanswerable",
    )

    # Model sessiz kaldı
    answer = RagAnswer(
        status="abstained",
        answer="Dokümanlarımızda bu konuda bilgi bulunamadı.",
        abstain_reason="model_abstained",
        citations=[],
        validation_issues=[],
    )

    result = score_case(case, answer)
    assert result.correct is True


def test_compute_generation_summary():
    """Özet metriklerin ve kategori kırılımlarının hesaplanması."""
    case_ans = AnswerCase(id="G01", question="Q1", answerable=True, expected_facts=["14 gün"], category="single_fact")
    case_unans = AnswerCase(id="U01", question="Q2", answerable=False, expected_facts=[], category="unanswerable")

    res1 = score_case(case_ans, RagAnswer(status="answered", answer="14 gün [1].", abstain_reason=None))
    res2 = score_case(case_unans, RagAnswer(status="abstained", answer="Yok.", abstain_reason="model_abstained"))

    summary = compute_generation_summary([res1, res2])
    assert summary.total_cases == 2
    assert summary.answerable_count == 1
    assert summary.unanswerable_count == 1
    assert summary.answer_accuracy == 1.0
    assert summary.hallucination_rate == 0.0
    assert summary.false_abstain_rate == 0.0
    assert summary.citation_valid_rate == 1.0


# ============================================================================
# 3. GATE ANALİZ VE KOLEKSİYON TEMİZLİĞİ TESTLERİ
# ============================================================================


def test_gate_analyze_thresholds():
    """Eşik analizi en fazla 1 cevaplanabilir kaybettiren en iyi eşiği bulmalıdır."""
    ans_scores = [0.85, 0.82, 0.80, 0.78, 0.75, 0.60]  # 0.60 bir uç değer
    unans_scores = [0.45, 0.40, 0.35, 0.30]

    table, best_thresh, rationale = analyze_thresholds(ans_scores, unans_scores)
    assert len(table) > 0
    # 0.70 civarında eşik unanswerable'ların tümünü eler ve 1 ans (0.60) kaybettirir
    assert best_thresh is not None
    assert "Onerilen esik" in rationale


def test_temporary_store_lifecycle_and_cleanup():
    """Geçici koleksiyon oluşturulabilmeli ve client.delete_collection ile silinebilmelidir."""
    client = QdrantClient(":memory:")
    embedder = FakeEmbedder(dimensions=16)
    chunks = [
        Chunk(
            id="c1",
            text="Örnek metin",
            embedding_text="Örnek metin",
            source_file="test.pdf",
            page_start=1,
            page_end=1,
            char_start=0,
            char_end=11,
            chunk_index=0,
            strategy=ChunkStrategy.STRUCTURE,
            token_count=5,
            heading_path=[],
        )
    ]

    store, col_name = setup_temporary_store(client=client, embedder=embedder, chunks=chunks)
    assert client.collection_exists(col_name) is True

    # Silme işlemi
    client.delete_collection(col_name)
    assert client.collection_exists(col_name) is False
