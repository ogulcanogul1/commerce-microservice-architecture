from pathlib import Path
import pytest
from pydantic import ValidationError

from app.rag.evaluation.chunking.dataset import (
    GoldenQuestion,
    load_golden_set,
    normalize_for_match,
    validate_golden_set,
)


def test_normalize_for_match_turkish_and_whitespace():
    # Türkçe İ ve I harflerinin doğru küçültülmesi
    assert normalize_for_match("IŞIK") == "ışık"
    assert normalize_for_match("İSTANBUL") == "istanbul"

    # Fazla ve karmaşık boşlukların sadeleştirilmesi
    text_with_spaces = "   Merhaba    dünya!\n\nBu   bir   testtir.   "
    assert normalize_for_match(text_with_spaces) == "merhaba dünya! bu bir testtir."


def test_golden_question_validation():
    # Geçerli soru
    q = GoldenQuestion(
        id="Q01",
        question="İade süresi kaç gündür?",
        doc="iade.pdf",
        evidence=["14 gün içinde iade edilir."],
        category="single_fact",
    )
    assert q.id == "Q01"
    assert q.category == "single_fact"

    # Boş soru hata vermeli
    with pytest.raises(ValidationError, match="Soru boş olamaz"):
        GoldenQuestion(
            id="Q02",
            question="   ",
            doc="iade.pdf",
            evidence=["delil"],
            category="single_fact",
        )

    # Geçersiz kategori hata vermeli
    with pytest.raises(ValidationError):
        GoldenQuestion(
            id="Q03",
            question="Geçersiz kategori sorusu?",
            doc="iade.pdf",
            evidence=["delil"],
            category="gecersiz_kategori",  # type: ignore
        )


def test_load_and_validate_real_golden_set():
    root = Path(__file__).resolve().parents[2]
    json_path = root / "eval" / "chunking" / "golden_set.json"
    docs_dir = root / "eval" / "chunking" / "docs"

    assert json_path.is_file(), "golden_set.json dosyası mevcut olmalıdır."

    questions = load_golden_set(json_path)
    assert len(questions) >= 40

    is_valid, errors = validate_golden_set(json_path, docs_dir)
    assert is_valid is True, f"Validation errors found: {errors}"
    assert len(errors) == 0
