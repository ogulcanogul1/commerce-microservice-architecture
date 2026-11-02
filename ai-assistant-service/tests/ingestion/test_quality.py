from pathlib import Path

from app.rag.ingestion.pdf.quality import build_report, calculate_suspect_char_ratio
from app.rag.ingestion.pdf.triage import find_empty_pages, page_char_counts


def test_calculate_suspect_char_ratio_clean_text():
    """Clean text with regular whitespace and newlines has zero suspect ratio."""
    text = "Kuzey Market E-Ticaret Platformu\n\nStandart paragraf.\tTab boslugu."
    ratio = calculate_suspect_char_ratio(text)
    assert ratio == 0.0


def test_calculate_suspect_char_ratio_with_corrupt_chars():
    """Text with Unicode replacement characters has positive suspect ratio."""
    # 20 normal characters + 5 replacement chars = 25 chars total -> 5/25 = 0.20 (20%)
    text = "Normal metin burasi." + ("\ufffd" * 5)
    ratio = calculate_suspect_char_ratio(text)
    assert ratio == 0.2


def test_build_report_quarantines_scanned_pdf(scanned_like_pdf: Path):
    """Scanned-like PDF (100% empty pages) is quarantined with 'too_many_empty_pages' and 'no_elements'."""
    counts = page_char_counts(scanned_like_pdf)
    empty_pages = find_empty_pages(counts)

    report = build_report(
        page_count=len(counts),
        empty_pages=empty_pages,
        full_text="",
        element_count=0,
    )

    assert report.status == "quarantine"
    assert "too_many_empty_pages" in report.reasons
    assert "no_elements" in report.reasons
    assert report.empty_pages == [1]


def test_build_report_ok_for_two_column_pdf(two_column_pdf: Path):
    """Healthy two-column PDF without empty pages or corrupt characters passes as 'ok'."""
    counts = page_char_counts(two_column_pdf)
    empty_pages = find_empty_pages(counts)

    report = build_report(
        page_count=len(counts),
        empty_pages=empty_pages,
        full_text="Two column text content without corrupt characters.",
        element_count=2,
    )

    assert report.status == "ok"
    assert report.reasons == []
    assert report.empty_pages == []
    assert report.suspect_char_ratio == 0.0


def test_build_report_quarantines_garbled_text():
    """Document with suspect characters exceeding 2% is quarantined with 'garbled_text'."""
    corrupted_text = ("A" * 95) + ("\ufffd" * 5)
    report = build_report(
        page_count=1,
        empty_pages=[],
        full_text=corrupted_text,
        element_count=1,
    )

    assert report.status == "quarantine"
    assert "garbled_text" in report.reasons


def test_build_report_quarantines_when_no_elements_produced():
    """Document that yields zero elements is quarantined with 'no_elements'."""
    report = build_report(
        page_count=1,
        empty_pages=[],
        full_text="",
        element_count=0,
    )

    assert report.status == "quarantine"
    assert "no_elements" in report.reasons
