from pathlib import Path
import pytest

from app.rag.ingestion.pdf.loader import PDFLoader


def test_pdf_loader_raises_when_file_not_found(tmp_path: Path):
    loader = PDFLoader()
    with pytest.raises(FileNotFoundError):
        loader.load_clean_pages(tmp_path / "non_existent.pdf")


def test_pdf_loader_cleans_cross_page_pdf(cross_page_pdf: Path):
    loader = PDFLoader()
    pages = loader.load_clean_pages(cross_page_pdf)

    assert len(pages) == 2

    # Verify 1-based page numbers
    assert pages[0][0] == 1
    assert pages[1][0] == 2

    page1_text = pages[0][1]
    page2_text = pages[1][1]

    # Verify repeated header and footer are eliminated
    assert "Kuzey Market Politika Kilavuzu" not in page1_text
    assert "Kuzey Market Politika Kilavuzu" not in page2_text
    assert "Sayfa 1" not in page1_text
    assert "Sayfa 2" not in page2_text

    # Verify dehyphenation merged split words
    assert "karsilanir" in page1_text
    assert "karsi-" not in page1_text

    # Verify main content is preserved
    assert "# 1. Iade Kosullari" in page1_text
    assert "odenir ve depoya ulasinca incelenir." in page2_text
