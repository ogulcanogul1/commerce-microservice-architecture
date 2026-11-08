"""Token bütçesi rezervasyon tahmin motoru (Token Estimator).

LLM çağrısı yapılmadan önce sorunun uzunluğuna, sistem prompt'una, araç şemalarına
ve olası maksimum çıktı uzunluğuna göre peşin rezerve edilecek tahmini token miktarını hesaplar.
"""

from __future__ import annotations

from typing import Any


def estimate_chat_tokens(
    message: str,
    tokenizer: Any,
    *,
    overhead: int = 1500,
    max_output: int = 1000,
    steps: int = 2,
) -> int:
    """Agent veya RAG sohbet turu için rezerve edilecek tahmini token sayısını hesaplar.
    
    Formül:
        (Sistem Prompt/Tool Gideri + Soru Metni Tokenı + Maksimum Çıktı Tokenı) * Adım Sayısı
    
    Parametreler:
        message: Kullanıcının girdiği doğal dil soru metni.
        tokenizer: count_tokens(text) metoduna sahip tokenizer nesnesi (örn. TiktokenTokenizer).
        overhead: Sistem prompt'u, güvenlik talimatları ve tool JSON şemaları için ayrılan tahmini token payı.
        max_output: LLM'in tek bir adımda üretebileceği izin verilen maksimum çıktı tokenı.
        steps: Tipik bir turda atılacak adım sayısı (Agent için genelde 2: tool çağrısı + nihai cevap, RAG için 1).
    """
    if tokenizer is not None and hasattr(tokenizer, "count_tokens"):
        try:
            prompt_tokens = tokenizer.count_tokens(message)
        except Exception:
            # Tokenizer patlarsa güvenli kaba tahmin: 1 kelime ~= 1.3 token
            prompt_tokens = int(len(message.split()) * 1.3)
    else:
        prompt_tokens = int(len(message.split()) * 1.3)

    single_step_tokens = overhead + prompt_tokens + max_output
    total_estimated = single_step_tokens * max(1, steps)

    return total_estimated
