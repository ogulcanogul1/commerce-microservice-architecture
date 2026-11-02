from app.rag.ingestion.pdf.cleaning import dehyphenate, normalize, remove_repeated_lines


def test_dehyphenate_merges_split_word_across_lines():
    text = "Müşteri memnuniyeti karşı-\nlanır ve süreç başlar."
    result = dehyphenate(text)
    assert "karşılanır" in result
    assert "karşı-" not in result


def test_dehyphenate_preserves_intra_word_hyphen():
    text = "Türkiye genelinde e-ticaret hacmi büyüyor."
    result = dehyphenate(text)
    assert result == text


def test_normalize_collapses_blank_lines_and_nfc():
    raw_text = "Başlık\n\n\n\n\nParagraf metni.\n\n\n"
    result = normalize(raw_text)
    assert result == "Başlık\n\nParagraf metni."


def test_remove_repeated_lines_cleans_headers_and_footers():
    page1 = (
        "Kuzey Market Politika Kılavuzu\n"
        "# 1. İade\n"
        "İade şartları gövde metni.\n"
        "Sayfa 1"
    )
    page2 = (
        "Kuzey Market Politika Kılavuzu\n"
        "# 2. Kargo\n"
        "Kargo şartları gövde metni.\n"
        "Sayfa 2"
    )

    cleaned = remove_repeated_lines([page1, page2])
    assert len(cleaned) == 2

    # Check headers and footers are gone
    for page in cleaned:
        assert "Kuzey Market Politika Kılavuzu" not in page
        assert "Sayfa" not in page

    # Check actual body text remains
    assert "# 1. İade" in cleaned[0]
    assert "İade şartları gövde metni." in cleaned[0]
    assert "# 2. Kargo" in cleaned[1]
    assert "Kargo şartları gövde metni." in cleaned[1]


def test_remove_repeated_lines_preserves_repeated_body_text_in_middle():
    """Repeated body notes in the middle of pages must never be removed as headers/footers."""
    page1 = (
        "Kuzey Market Politika Kılavuzu\n"  # Top margin line 0 (header -> removed)
        "# Bolum 1\n"
        "Giris aciklamasi.\n"
        "Not: iade 14 gun.\n"  # Body line (repeated -> PRESERVED!)
        "Detayli sartlar burada anlatilmistir.\n"
        "Sayfa 1"  # Bottom margin (footer -> removed)
    )
    page2 = (
        "Kuzey Market Politika Kılavuzu\n"  # Top margin line 0 (header -> removed)
        "# Bolum 2\n"
        "Kargo aciklamasi.\n"
        "Not: iade 14 gun.\n"  # Body line (repeated -> PRESERVED!)
        "Ekstra sartlar burada anlatilmistir.\n"
        "Sayfa 2"  # Bottom margin (footer -> removed)
    )

    cleaned = remove_repeated_lines([page1, page2])
    assert len(cleaned) == 2

    # Headers and footers must be stripped
    for page in cleaned:
        assert "Kuzey Market Politika Kılavuzu" not in page
        assert "Sayfa" not in page

    # Body note must be preserved on both pages
    assert "Not: iade 14 gun." in cleaned[0]
    assert "Not: iade 14 gun." in cleaned[1]


def test_remove_repeated_lines_preserves_table_separators_across_pages():
    """Table separators like |---|---| appear identically on every page but must never be removed."""
    page1 = (
        "Kuzey Market Rapor\n"
        "| Urun | Fiyat |\n"
        "|---|---|\n"
        "| Elma | 10 TL |\n"
        "Sayfa 1"
    )
    page2 = (
        "Kuzey Market Rapor\n"
        "| Urun | Fiyat |\n"
        "|---|---|\n"
        "| Armut | 20 TL |\n"
        "Sayfa 2"
    )

    cleaned = remove_repeated_lines([page1, page2])
    assert len(cleaned) == 2

    # Verify headers/footers were removed
    for page in cleaned:
        assert "Kuzey Market Rapor" not in page
        assert "Sayfa" not in page

    # Verify table separators are intact on both pages
    assert "|---|---|" in cleaned[0]
    assert "|---|---|" in cleaned[1]
    assert "| Elma | 10 TL |" in cleaned[0]
    assert "| Armut | 20 TL |" in cleaned[1]
