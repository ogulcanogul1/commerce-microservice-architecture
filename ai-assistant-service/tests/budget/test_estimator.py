"""Token estimator birim testleri."""

from __future__ import annotations

from app.budget.estimator import estimate_chat_tokens


class DummyTokenizer:
    def count_tokens(self, text: str) -> int:
        return len(text.split()) * 2


def test_estimate_chat_tokens_with_tokenizer():
    """Tokenizer ile doğru adım ve overhead hesabı yapılır."""
    tokenizer = DummyTokenizer()
    msg = "Siparişim nerede kaldı acaba"  # 4 kelime * 2 = 8 token

    # single step: 1500 (overhead) + 8 (prompt) + 1000 (max_output) = 2508
    # 2 steps: 2508 * 2 = 5016
    est = estimate_chat_tokens(
        msg,
        tokenizer,
        overhead=1500,
        max_output=1000,
        steps=2,
    )
    assert est == 5016


def test_estimate_chat_tokens_fallback():
    """Tokenizer None veya hatalı olduğunda kaba tahminle çalışır."""
    msg = "Bir iki üç dört beş"
    est = estimate_chat_tokens(
        msg,
        None,
        overhead=100,
        max_output=200,
        steps=1,
    )
    assert est > 300
