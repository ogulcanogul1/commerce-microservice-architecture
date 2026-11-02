from pathlib import Path

from app.rag.ingestion.pdf.loader import PDFLoader
from app.rag.ingestion.pdf.stitching import stitch_pages


def test_paragraph_stitching_unit():
    """Paragraph broken across pages without terminal punctuation should merge."""
    pages = [
        (1, "# 1. Giris\n\nBu kural geregince odeme musteri tarafindan"),
        (2, "yapilir ve siparis tamamlanir.\n\n## 2. Sonuc\n\nTesekkurler.")
    ]
    blocks = stitch_pages(pages)

    assert len(blocks) == 2
    # First block should contain the merged sentence with page_start=1 and page_end=2
    first_block_text, page_start, page_end = blocks[0]
    assert "odeme musteri tarafindan yapilir ve siparis tamamlanir." in first_block_text
    assert page_start == 1
    assert page_end == 2

    # Second block remains page 2
    second_block_text, p2_start, p2_end = blocks[1]
    assert "## 2. Sonuc" in second_block_text
    assert p2_start == 2
    assert p2_end == 2


def test_table_header_continuation_unit():
    """Table split across pages without headers should inherit headers from preceding page."""
    pages = [
        (1, "Bölüm Girişi\n\n| Urun | Fiyat |\n|---|---|\n| Elma | 10 TL |"),
        (2, "| Armut | 15 TL |\n| Kiraz | 20 TL |\n\nDiger icerik.")
    ]
    blocks = stitch_pages(pages)

    assert len(blocks) == 2
    p2_text, _, _ = blocks[1]
    # Page 2 table should now have the inherited header and separator
    assert "| Urun | Fiyat |" in p2_text
    assert "|---|---|" in p2_text
    assert "| Armut | 15 TL |" in p2_text


def test_no_stitching_when_sentence_ends_with_terminal_punctuation():
    """Sentences ending with '.', '!', '?', or ':' should not be merged across pages."""
    pages = [
        (1, "# 1. Tamamlanmis Paragraf.\n\nBu cumle kesin olarak bitti."),
        (2, "yeni baslayan ama ayri olan bir cumle.")
    ]
    blocks = stitch_pages(pages)

    assert len(blocks) == 2
    assert blocks[0][1] == 1
    assert blocks[0][2] == 1
    assert blocks[1][1] == 2
    assert blocks[1][2] == 2


def test_stitch_pages_with_cross_page_pdf(cross_page_pdf: Path):
    """Integration test with cross_page_pdf fixture verifying paragraph merging."""
    loader = PDFLoader()
    clean_pages = loader.load_clean_pages(cross_page_pdf)
    blocks = stitch_pages(clean_pages)

    # Find the block containing the stitched sentence
    stitched_block = None
    for text, p_start, p_end in blocks:
        if "musteri tarafindan odenir" in text:
            stitched_block = (text, p_start, p_end)
            break

    assert stitched_block is not None, "Stitched sentence was not found in blocks"
    text, page_start, page_end = stitched_block
    assert page_start == 1
    assert page_end == 2
    assert "kargo gonderim bedeli musteri tarafindan odenir ve depoya ulasinca incelenir." in text
