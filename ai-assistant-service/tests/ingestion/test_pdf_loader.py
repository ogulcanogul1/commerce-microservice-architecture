from pathlib import Path
import pytest

from app.rag.ingestion.base import DocumentLoader
from app.rag.ingestion.models import ElementType, ParsedDocument
from app.rag.ingestion.pdf.loader import PDFLoader


def test_pdf_loader_implements_document_loader_protocol():
    """PDFLoader must satisfy the runtime-checkable DocumentLoader protocol."""
    loader = PDFLoader()
    assert isinstance(loader, DocumentLoader)


def test_pdf_loader_raises_when_file_not_found(tmp_path: Path):
    """Attempting to load a non-existent file must raise FileNotFoundError."""
    loader = PDFLoader()
    with pytest.raises(FileNotFoundError):
        loader.load(tmp_path / "non_existent.pdf")


def test_pdf_loader_quarantines_scanned_pdf(scanned_like_pdf: Path):
    """Scanned PDF with no text must produce a quarantined ParsedDocument."""
    loader = PDFLoader()
    doc = loader.load(scanned_like_pdf)

    assert isinstance(doc, ParsedDocument)
    assert doc.quality.status == "quarantine"
    assert "too_many_empty_pages" in doc.quality.reasons
    assert len(doc.elements) == 0


def test_pdf_loader_end_to_end_cross_page_pdf(cross_page_pdf: Path):
    """End-to-end test verifying full ingestion pipeline on cross_page_pdf."""
    loader = PDFLoader()
    doc = loader.load(cross_page_pdf)

    # 1. Verification of document metadata
    assert isinstance(doc, ParsedDocument)
    assert doc.source_file == "cross_page.pdf"
    assert doc.parser_name == "pymupdf4llm"
    assert doc.parser_version != ""
    assert doc.quality.status == "ok"
    assert doc.quality.empty_pages == []

    # 2. Verify repeated headers and footers are eliminated from all elements
    for el in doc.elements:
        assert "Kuzey Market Politika Kilavuzu" not in el.text
        assert "Sayfa 1" not in el.text
        assert "Sayfa 2" not in el.text

    # 3. Verify dehyphenation was applied
    all_text = " ".join(el.text for el in doc.elements)
    assert "karsilanir" in all_text
    assert "karsi-" not in all_text

    # 4. Verify cross-page sentence stitching
    # The broken sentence should be in a single PARAGRAPH spanning page 1 to 2
    stitched_element = next(
        (
            el
            for el in doc.elements
            if "kargo gonderim bedeli musteri tarafindan odenir" in el.text
        ),
        None,
    )
    assert stitched_element is not None, "Stitched paragraph element was not found"
    assert stitched_element.type == ElementType.PARAGRAPH
    assert stitched_element.page_start == 1
    assert stitched_element.page_end == 2

    # 5. Verify table elements
    table_elements = [el for el in doc.elements if el.type == ElementType.TABLE]
    assert len(table_elements) >= 1
    first_table = table_elements[0]
    # First table must start with column headers
    assert first_table.text.startswith("| Urun Grubu | Garanti Suresi |")

    # 6. Verify heading hierarchy and page isolation
    h1_element = next(
        (el for el in doc.elements if el.type == ElementType.HEADING and "1. Iade Kosullari" in el.text),
        None,
    )
    assert h1_element is not None
    assert h1_element.heading_path == []
    # Heading on page 1 must remain strictly page 1 (no page range explosion)
    assert h1_element.page_start == 1 and h1_element.page_end == 1

    # Elements under H1 must have ["1. Iade Kosullari"] in their heading_path
    assert stitched_element.heading_path == ["1. Iade Kosullari"]
