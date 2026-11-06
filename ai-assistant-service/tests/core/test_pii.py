from app.core.pii import mask_pii, validate_luhn, validate_tckn_checksum


def test_tckn_validation_logic() -> None:
    # Sentetik geçerli numara
    assert validate_tckn_checksum("54321098710") is True
    # Checksum tutmayan 11 haneli numara
    assert validate_tckn_checksum("12345678901") is False
    # İlk hanesi 0 olan
    assert validate_tckn_checksum("01234567890") is False
    # 11 haneden kısa / uzun
    assert validate_tckn_checksum("5432109871") is False
    assert validate_tckn_checksum("543210987100") is False


def test_tckn_masking() -> None:
    # Geçerli TCKN maskelenmeli
    text, pii_types = mask_pii("Müşteri kimlik no: 54321098710.")
    assert text == "Müşteri kimlik no: [TCKN]."
    assert pii_types == ["tckn"]

    # Checksum tutmayan 11 haneli sayı (sipariş no vb.) maskelenmemeli
    raw_order = "Siparişim 12345678901 nolu pakettir."
    text_unmasked, types_unmasked = mask_pii(raw_order)
    assert text_unmasked == raw_order
    assert types_unmasked == []


def test_card_validation_and_masking() -> None:
    # Luhn tutan kartlar
    assert validate_luhn("4532015112830366") is True
    # Luhn tutmayan kart
    assert validate_luhn("1234567890123457") is False

    # Tireli kart maskelenmeli
    text_dash, types_dash = mask_pii("Kartım: 4532-0151-1283-0366 ile ödeme yapıldı.")
    assert text_dash == "Kartım: [KART] ile ödeme yapıldı."
    assert types_dash == ["card"]

    # Boşluklu kart maskelenmeli
    text_space, types_space = mask_pii("Kartım: 4532 0151 1283 0366 ile ödeme yapıldı.")
    assert text_space == "Kartım: [KART] ile ödeme yapıldı."
    assert types_space == ["card"]

    # Luhn tutmayan 16 hane maskelenmemeli
    bad_card = "Seri no 1234567890123457 kontrol edilsin."
    text_bad, types_bad = mask_pii(bad_card)
    assert text_bad == bad_card
    assert types_bad == []


def test_iban_masking() -> None:
    # Boşluklu IBAN
    text, pii_types = mask_pii("İadeyi TR33 0006 1005 1234 5678 9012 34 hesabıma yapın.")
    assert text == "İadeyi [IBAN] hesabıma yapın."
    assert pii_types == ["iban"]

    # Bitişik IBAN
    text2, pii_types2 = mask_pii("TR330006100512345678901234 nolu hesap")
    assert text2 == "[IBAN] nolu hesap"
    assert pii_types2 == ["iban"]


def test_phone_masking() -> None:
    # +90 ile bitişik
    text1, types1 = mask_pii("Telefonum +905321234567 arayabilirsiniz.")
    assert text1 == "Telefonum [TELEFON] arayabilirsiniz."
    assert types1 == ["phone"]

    # 0 ile boşluklu
    text2, types2 = mask_pii("İletişim: 0532 123 45 67 lütfen.")
    assert text2 == "İletişim: [TELEFON] lütfen."
    assert types2 == ["phone"]


def test_email_masking() -> None:
    text, pii_types = mask_pii("Bana musteri.destek@commerce.com adresinden yazın.")
    assert text == "Bana [EPOSTA] adresinden yazın."
    assert pii_types == ["email"]


def test_business_queries_remain_unmodified() -> None:
    # Sipariş no, süre ve tutar içeren iş sorgusu değişmemeli
    query = "Siparişim 12345 ne zaman gelir? İade süresi 14 gün mü ve 1.000 TL üzeri mi?"
    masked, pii_types = mask_pii(query)
    assert masked == query
    assert pii_types == []


def test_multiple_pii_types_in_single_text_order_preserved() -> None:
    query = (
        "Adım Ali, e-postam ali@test.com, TCKN: 54321098710, "
        "kartım 4532-0151-1283-0366 ve tel: 0532 123 45 67."
    )
    masked, pii_types = mask_pii(query)
    assert masked == (
        "Adım Ali, e-postam [EPOSTA], TCKN: [TCKN], "
        "kartım [KART] ve tel: [TELEFON]."
    )
    # Metindeki ilk görülme sırası korunmalı: email, tckn, card, phone
    assert pii_types == ["email", "tckn", "card", "phone"]


def test_empty_or_none_text() -> None:
    assert mask_pii("") == ("", [])
