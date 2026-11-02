from app.rag.ingestion.models import ElementType
from app.rag.ingestion.pdf.elements import parse_markdown_to_elements


def test_parse_markdown_to_elements_types_and_heading_path():
    """Verifies that markdown is converted to correct element types with proper heading paths."""
    markdown = (
        "# 1. Ana Bolum\n\n"
        "Bu ana bolumun giris paragrafidir.\n\n"
        "## 1.1 Alt Baslik\n\n"
        "Alt baslik altindaki aciklama metni.\n\n"
        "| Urun | Fiyat |\n"
        "|---|---|\n"
        "| Defter | 20 TL |\n"
        "| Silgi | 5 TL |\n\n"
        "- Madde 1: Fatura zorunlu\n"
        "- Madde 2: Kutusu acilmamis\n\n"
        "# 2. Ikinci Bolum\n\n"
        "Ikinci bolum icerigi buradadir."
    )

    blocks = [(markdown, 1, 1)]
    elements = parse_markdown_to_elements(blocks)

    # Expected element types in sequence:
    # 0: HEADING (1. Ana Bolum)
    # 1: PARAGRAPH (Bu ana bolumun...)
    # 2: HEADING (1.1 Alt Baslik)
    # 3: PARAGRAPH (Alt baslik altindaki...)
    # 4: TABLE (| Urun | Fiyat |...)
    # 5: LIST (- Madde 1...)
    # 6: HEADING (2. Ikinci Bolum)
    # 7: PARAGRAPH (Ikinci bolum icerigi...)

    assert len(elements) == 8

    # 0. H1
    assert elements[0].type == ElementType.HEADING
    assert elements[0].text == "1. Ana Bolum"
    assert elements[0].heading_path == []

    # 1. Paragraph under H1
    assert elements[1].type == ElementType.PARAGRAPH
    assert "Bu ana bolumun giris paragrafidir." in elements[1].text
    assert elements[1].heading_path == ["1. Ana Bolum"]

    # 2. H2
    assert elements[2].type == ElementType.HEADING
    assert elements[2].text == "1.1 Alt Baslik"
    assert elements[2].heading_path == ["1. Ana Bolum"]

    # 3. Paragraph under H2
    assert elements[3].type == ElementType.PARAGRAPH
    assert elements[3].heading_path == ["1. Ana Bolum", "1.1 Alt Baslik"]

    # 4. Table under H2
    assert elements[4].type == ElementType.TABLE
    assert "| Defter | 20 TL |" in elements[4].text
    assert elements[4].heading_path == ["1. Ana Bolum", "1.1 Alt Baslik"]

    # 5. List under H2
    assert elements[5].type == ElementType.LIST
    assert "- Madde 1: Fatura zorunlu" in elements[5].text
    assert elements[5].heading_path == ["1. Ana Bolum", "1.1 Alt Baslik"]

    # 6. H1 (Second chapter, resets heading stack)
    assert elements[6].type == ElementType.HEADING
    assert elements[6].text == "2. Ikinci Bolum"
    assert elements[6].heading_path == []

    # 7. Paragraph under second H1
    assert elements[7].type == ElementType.PARAGRAPH
    assert elements[7].heading_path == ["2. Ikinci Bolum"]


def test_elements_preserve_page_range_from_stitched_block():
    """Elements created from a stitched block spanning multiple pages retain page_start and page_end."""
    stitched_text = "Bu cumle birden fazla sayfaya yayilmistir."
    blocks = [(stitched_text, 1, 3)]

    elements = parse_markdown_to_elements(blocks)
    assert len(elements) == 1
    assert elements[0].type == ElementType.PARAGRAPH
    assert elements[0].page_start == 1
    assert elements[0].page_end == 3
