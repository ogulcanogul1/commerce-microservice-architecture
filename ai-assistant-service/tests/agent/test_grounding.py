from app.agent.grounding import check_reply_grounding


def test_grounding_happy_path_all_numbers_exist() -> None:
    reply = "Siparişinizde 2 adet ürün bulunuyor ve toplam tutar 1500 TL."
    tool_results = ['{"total_amount": 1500.0, "item_count": 2}']

    issues = check_reply_grounding(reply, tool_results, tools_called=True)
    assert issues == []


def test_grounding_detects_hallucinated_number() -> None:
    reply = "Siparişiniz 3 gün içinde teslim edilecek ve 1500 TL tutarındadır."
    tool_results = ['{"total_amount": 1500.0}']  # "3" sayısı yok

    issues = check_reply_grounding(reply, tool_results, tools_called=True)
    assert len(issues) == 1
    assert "«3» sayısı araç sonuçlarında geçmiyor." in issues[0]


def test_grounding_detects_numbers_when_no_tools_called() -> None:
    reply = "Siparişiniz 5 gün sonra teslim edilecektir."
    tool_results: list[str] = []

    # Araç çağrılmadan kafadan sayı sallanırsa
    issues = check_reply_grounding(reply, tool_results, tools_called=False)
    assert len(issues) == 1
    assert issues[0] == "Araç çağırmadan sayısal bilgi verildi."


def test_grounding_allows_text_without_numbers_even_if_no_tools_called() -> None:
    reply = "Merhaba! Size nasıl yardımcı olabilirim?"
    tool_results: list[str] = []

    issues = check_reply_grounding(reply, tool_results, tools_called=False)
    assert issues == []


def test_grounding_turkish_currency_formats_accepted() -> None:
    """Türkçe para birimi formatları (1.299,90 TL, 1299,90 TL, 150,00 TL) ayırıcılardan bağımsız geçerli olmalıdır."""
    tool_results = ['{"total_amount": "1299.90", "item_count": 2}']

    # 1. '1.299,90 TL' formatı
    reply1 = "Siparişinizin toplam tutarı 1.299,90 TL'dir ve 2 adet ürün içerir."
    assert check_reply_grounding(reply1, tool_results, tools_called=True) == []

    # 2. '1299,90 TL' formatı (noktasız virgüllü)
    reply2 = "Sipariş tutarınız 1299,90 TL olarak görüntülenmektedir."
    assert check_reply_grounding(reply2, tool_results, tools_called=True) == []

    # 3. '150,00 TL' formatı (sıfırlı kuruş)
    tool_results_round = ['{"total_amount": "150.00"}']
    reply3 = "Kargo ücreti dahil toplam 150,00 TL tahsil edilmiştir."
    assert check_reply_grounding(reply3, tool_results_round, tools_called=True) == []

    # 4. '150 TL' tam sayı formatı
    reply4 = "Toplam tutarınız 150 TL."
    assert check_reply_grounding(reply4, tool_results_round, tools_called=True) == []


def test_grounding_turkish_currency_hallucination_detected() -> None:
    """Türkçe para formatında yazılsa bile araç sonucunda olmayan uydurma tutarlar yakalanmalıdır."""
    tool_results = ['{"total_amount": "1299.90"}']

    # Model 1299.90 yerine 2.500,00 TL uydurursa
    reply = "Siparişinizin toplam tutarı 2.500,00 TL'dir."
    issues = check_reply_grounding(reply, tool_results, tools_called=True)

    assert len(issues) == 1
    assert "«2.500,00» sayısı araç sonuçlarında geçmiyor." in issues[0]
