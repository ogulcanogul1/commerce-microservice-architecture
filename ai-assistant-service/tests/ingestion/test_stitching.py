from pathlib import Path

from app.rag.ingestion.models import Element, ElementType
from app.rag.ingestion.pdf.loader import PDFLoader
from app.rag.ingestion.pdf.elements import parse_markdown_to_elements
from app.rag.ingestion.pdf.stitching import stitch_elements


def test_paragraph_stitching_and_page_isolation():
    """Only the broken paragraph stitches across pages, preceding headings remain 1->1."""
    raw_elements = [
        Element(type=ElementType.HEADING, text="1. Bolum", page_start=1, page_end=1),
        Element(
            type=ElementType.PARAGRAPH,
            text="Bu kural geregince odeme musteri tarafindan",
            page_start=1,
            page_end=1,
        ),
        Element(
            type=ElementType.PARAGRAPH,
            text="yapilir ve siparis onaylanir.",
            page_start=2,
            page_end=2,
        ),
        Element(type=ElementType.HEADING, text="2. Bolum", page_start=2, page_end=2),
    ]

    stitched = stitch_elements(raw_elements)

    assert len(stitched) == 3

    # Heading on Page 1 must strictly remain page 1->1
    assert stitched[0].type == ElementType.HEADING
    assert stitched[0].page_start == 1 and stitched[0].page_end == 1

    # Stitched paragraph expands to page 1->2
    assert stitched[1].type == ElementType.PARAGRAPH
    assert stitched[1].page_start == 1 and stitched[1].page_end == 2
    assert "odeme musteri tarafindan yapilir ve siparis onaylanir." in stitched[1].text

    # Heading on Page 2 must strictly remain page 2->2
    assert stitched[2].type == ElementType.HEADING
    assert stitched[2].page_start == 2 and stitched[2].page_end == 2


def test_paragraph_stitching_merges_cross_page_hyphen():
    """Hyphen broken across page boundary is merged during element stitching."""
    raw_elements = [
        Element(
            type=ElementType.PARAGRAPH,
            text="Tum masraflar firmamizca karsi-",
            page_start=1,
            page_end=1,
        ),
        Element(
            type=ElementType.PARAGRAPH,
            text="lanir ve hesap kapatilir.",
            page_start=2,
            page_end=2,
        ),
    ]

    stitched = stitch_elements(raw_elements)
    assert len(stitched) == 1
    assert "karsilanir" in stitched[0].text
    assert "karsi-" not in stitched[0].text
    assert stitched[0].page_start == 1 and stitched[0].page_end == 2


def test_no_stitching_when_pages_are_not_consecutive():
    """Gaps between non-consecutive pages (e.g. page 1 and page 3) must never be stitched."""
    raw_elements = [
        Element(
            type=ElementType.PARAGRAPH,
            text="Cumle yarim kalsa bile",
            page_start=1,
            page_end=1,
        ),
        Element(
            type=ElementType.PARAGRAPH,
            text="devam edemez cunku sayfa 2 atlandi.",
            page_start=3,
            page_end=3,
        ),
    ]

    stitched = stitch_elements(raw_elements)
    assert len(stitched) == 2
    assert stitched[0].page_start == 1 and stitched[0].page_end == 1
    assert stitched[1].page_start == 3 and stitched[1].page_end == 3


def test_no_stitching_between_different_element_types():
    """Table row followed by lowercase paragraph must never be merged."""
    raw_elements = [
        Element(
            type=ElementType.TABLE,
            text="| Urun | Fiyat |\n|---|---|\n| Elma | 10 TL |",
            page_start=1,
            page_end=1,
        ),
        Element(
            type=ElementType.PARAGRAPH,
            text="ve sonraki aciklama metni.",
            page_start=2,
            page_end=2,
        ),
    ]

    stitched = stitch_elements(raw_elements)
    assert len(stitched) == 2
    assert stitched[0].type == ElementType.TABLE
    assert stitched[1].type == ElementType.PARAGRAPH


def test_table_continuation_stitching():
    """Consecutive tables on adjacent pages are merged into a single table."""
    raw_elements = [
        Element(
            type=ElementType.TABLE,
            text="| Urun | Fiyat |\n|---|---|\n| Elma | 10 TL |",
            page_start=1,
            page_end=1,
        ),
        Element(
            type=ElementType.TABLE,
            text="| Armut | 20 TL |\n| Kiraz | 30 TL |",
            page_start=2,
            page_end=2,
        ),
    ]

    stitched = stitch_elements(raw_elements)
    assert len(stitched) == 1
    assert stitched[0].type == ElementType.TABLE
    assert stitched[0].page_start == 1 and stitched[0].page_end == 2
    assert "| Elma | 10 TL |" in stitched[0].text
    assert "| Armut | 20 TL |" in stitched[0].text
