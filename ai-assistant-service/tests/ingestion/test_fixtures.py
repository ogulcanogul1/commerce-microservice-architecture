from pathlib import Path
import pymupdf


def test_two_column_pdf_creation(two_column_pdf: Path):
    doc = pymupdf.open(str(two_column_pdf))
    assert doc.page_count == 1
    doc.close()


def test_cross_page_pdf_creation(cross_page_pdf: Path):
    doc = pymupdf.open(str(cross_page_pdf))
    assert doc.page_count == 2
    doc.close()


def test_scanned_like_pdf_creation(scanned_like_pdf: Path):
    doc = pymupdf.open(str(scanned_like_pdf))
    assert doc.page_count == 1
    text = doc[0].get_text().strip()
    assert text == ""
    doc.close()
