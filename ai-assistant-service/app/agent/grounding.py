"""Grounding verification for agent responses against tool outputs.

Prevents numerical hallucinations (fake dates, amounts, days, order numbers)
by verifying that all numbers mentioned in the LLM response exist in tool results,
with full separator-independent support for Turkish and international currency/number formats.
"""

from __future__ import annotations

import re


def _generate_allowed_number_representations(corpus: str) -> set[str]:
    """Extract and generate all valid format variations of numbers present in tool outputs."""
    allowed: set[str] = set()

    # 1. Ham rakam dizileri (tüm \d+ parçaları)
    for d in re.findall(r"\d+", corpus):
        allowed.add(d)

    # 2. Tam sayısal ifadeler (tutar, ondalık, vb.)
    for tok in re.findall(r"\d+(?:[.,]\d+)*", corpus):
        allowed.add(tok)

        # 07, 00 gibi padded kod/tarih parçalarını floata dönüştürme (07 -> 7 olmamalı)
        if tok.startswith("0") and len(tok) > 1 and not (tok.startswith("0.") or tok.startswith("0,")):
            continue

        try:
            val_str = tok.replace(",", ".") if ("," in tok and "." not in tok) else tok
            f = float(val_str)
            allowed.add(f"{f:.2f}")
            allowed.add(f"{f:.1f}")
            if f.is_integer():
                allowed.add(f"{int(f)}")

            # Türkçe para birimi varyasyonları (1.299,90 ve 1299,90)
            parts = f"{f:.2f}".split(".")
            int_part = parts[0]
            dec_part = parts[1]
            formatted_thousands = f"{int(int_part):,}".replace(",", ".")
            allowed.add(f"{formatted_thousands},{dec_part}")
            allowed.add(f"{int_part},{dec_part}")
            # Binlik ayırıcılı tam sayı biçimi (ör. 1.299 TL veya 1.500 TL)
            allowed.add(formatted_thousands)
        except Exception:
            pass

    return allowed


def check_reply_grounding(
    reply: str,
    tool_results: list[str],
    *,
    tools_called: bool,
) -> list[str]:
    """Verify that all numerical sequences in the response are grounded in tool results.

    Supports Turkish currency formatting (e.g., '1.299,90 TL', '1299,90', '150,00')
    in a separator-independent manner against tool outputs.

    Returns:
        list[str]: Detected grounding violations, empty if valid.
    """
    issues: list[str] = []

    # Model yanıtındaki sayı ve tutar tokenlarını ayıkla (1.299,90 veya 1500 veya 7)
    reply_tokens = re.findall(r"\d+(?:[.,]\d+)*", reply)
    if not reply_tokens:
        return issues

    if not tools_called:
        issues.append("Araç çağırmadan sayısal bilgi verildi.")
        return issues

    corpus = " ".join(tool_results)
    allowed_numbers = _generate_allowed_number_representations(corpus)

    seen_violations: set[str] = set()
    for tok in reply_tokens:
        # Doğrudan izin verilen varyasyonlardan birinde var mı?
        if tok in allowed_numbers:
            continue

        # Model Türkçe biçimde '1.299,90', '1.299' veya '150,00' yazdıysa normalize edip bak
        matched = False
        try:
            if "." in tok and "," in tok:
                val_str = tok.replace(".", "").replace(",", ".")
            elif "." in tok and len(tok.split(".")[1]) == 3:
                val_str = tok.replace(".", "")
            else:
                val_str = tok.replace(",", ".")

            f = float(val_str)
            if (
                f"{f:.2f}" in allowed_numbers
                or (f.is_integer() and f"{int(f)}" in allowed_numbers)
                or tok in allowed_numbers
            ):
                matched = True
        except Exception:
            pass

        if not matched and tok not in seen_violations:
            seen_violations.add(tok)
            issues.append(f"«{tok}» sayısı araç sonuçlarında geçmiyor.")

    return issues
