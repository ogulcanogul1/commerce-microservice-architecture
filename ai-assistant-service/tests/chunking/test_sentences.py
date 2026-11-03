import pytest
from app.rag.chunking.sentences import split_sentences


def test_empty_and_whitespace_text():
    assert split_sentences("") == []
    assert split_sentences("   ") == [(0, 3)]


def test_single_sentence():
    text = "Bu tek bir cümleden oluşan bir metindir."
    spans = split_sentences(text)
    assert len(spans) == 1
    assert spans[0] == (0, len(text))
    assert text[spans[0][0] : spans[0][1]] == text


def test_abbreviation_protection():
    text = "Dr. Ahmet Bey ve Prof. Kaya toplantıya katıldılar. Karar oy birliğiyle alındı."
    spans = split_sentences(text)
    assert len(spans) == 2
    assert "Dr. Ahmet" in text[spans[0][0] : spans[0][1]]
    assert "Prof. Kaya" in text[spans[0][0] : spans[0][1]]
    assert text[spans[1][0] : spans[1][1]] == "Karar oy birliğiyle alındı."
    assert "".join(text[s:e] for s, e in spans) == text


def test_decimal_numbers_protection():
    text = "Ürünün ağırlığı 3.5 kg olarak tartıldı. Fiyatı 1.250,50 TL olarak belirlendi."
    spans = split_sentences(text)
    assert len(spans) == 2
    assert "3.5 kg" in text[spans[0][0] : spans[0][1]]
    assert "1.250,50 TL" in text[spans[1][0] : spans[1][1]]
    assert "".join(text[s:e] for s, e in spans) == text


def test_date_protection():
    text = "İade süresi 14.02.2026 tarihinde sona erecektir. Lütfen gecikmeyiniz."
    spans = split_sentences(text)
    assert len(spans) == 2
    assert "14.02.2026" in text[spans[0][0] : spans[0][1]]
    assert "".join(text[s:e] for s, e in spans) == text


def test_section_numbering_protection():
    text = "Madde 4.1 İade şartlarını düzenler. Müşteri bu şartlara uymakla yükümlüdür."
    spans = split_sentences(text)
    assert len(spans) == 2
    assert "Madde 4.1 İade" in text[spans[0][0] : spans[0][1]]
    assert "".join(text[s:e] for s, e in spans) == text


def test_question_and_exclamation_marks():
    text = "Siparişi teslim aldınız mı? Kutuyu henüz açmayın! Servis çağırınız."
    spans = split_sentences(text)
    assert len(spans) == 3
    assert text[spans[0][0] : spans[0][1]].strip() == "Siparişi teslim aldınız mı?"
    assert text[spans[1][0] : spans[1][1]].strip() == "Kutuyu henüz açmayın!"
    assert text[spans[2][0] : spans[2][1]].strip() == "Servis çağırınız."
    assert "".join(text[s:e] for s, e in spans) == text


def test_ellipsis_protection():
    text = "Süreç devam ediyor... Sonuç yarın bildirilecek."
    spans = split_sentences(text)
    assert len(spans) == 2
    assert text[spans[0][0] : spans[0][1]].strip() == "Süreç devam ediyor..."
    assert text[spans[1][0] : spans[1][1]].strip() == "Sonuç yarın bildirilecek."
    assert "".join(text[s:e] for s, e in spans) == text


def test_turkish_uppercase_letters():
    text = "İşlem tamamlandı. Ürün kargoya verildi. Şikayet formu dolduruldu. Çıkış yapıldı."
    spans = split_sentences(text)
    assert len(spans) == 4
    sentences = [text[s:e].strip() for s, e in spans]
    assert sentences == [
        "İşlem tamamlandı.",
        "Ürün kargoya verildi.",
        "Şikayet formu dolduruldu.",
        "Çıkış yapıldı.",
    ]
    assert "".join(text[s:e] for s, e in spans) == text


def test_seamless_coverage():
    """Verify that concatenating all slices completely and identically recovers the source text."""
    text = (
        "Merhaba sn. Müşteri! 12.05.2025 tarihli siparişiniz (No. 4589) hazırlandı. "
        "Ağırlık: 4.8 kg. İade süresi 14 gündür... Teşekkür ederiz."
    )
    spans = split_sentences(text)
    reconstructed = "".join(text[s:e] for s, e in spans)
    assert reconstructed == text


# ==============================================================================
# KNOWN LIMITATIONS (Belgelenmiş Kısıtlamalar)
# ==============================================================================
# 1. KNOWN LIMITATION: Kısaltma bir cümlenin en son kelimesi olduğunda (örneğin
#    "Toplantıya katılan Dr. Ayşe Hanım idi." yerine "Toplantıya katıldı Dr."),
#    kısaltma koruması noktayı cümle sonu saymaz ve sonraki cümleyle birleştirebilir.
# 2. KNOWN LIMITATION: Alıntı içinde tırnak işaretiyle biten cümlelerde ("Gidiyorum." dedi.)
#    noktadan sonra hemen tırnak geldiği için cümle tırnaktan sonra bölünebilir.
