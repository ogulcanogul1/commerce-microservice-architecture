"""Grounding verification for agent responses against tool outputs.

Prevents numerical hallucinations (fake dates, amounts, days, order numbers)
by verifying that all numbers mentioned in the LLM response exist in tool results,
with full separator-independent support for Turkish and international currency/number formats.
"""

from __future__ import annotations

import math
import re


def _parse_candidate_floats(token: str) -> list[float]:
    """Parse candidate float values from a numeric token with various separator conventions."""
    vals: list[float] = []

    # 1. Pure integer
    if token.isdigit():
        vals.append(float(token))
        return vals

    # 2. Both dot and comma present
    if "." in token and "," in token:
        dot_idx = token.find(".")
        comma_idx = token.find(",")
        if dot_idx < comma_idx:
            # Turkish/European format: 1.299,90 -> remove '.', replace ',' with '.'
            try:
                vals.append(float(token.replace(".", "").replace(",", ".")))
            except ValueError:
                pass
        else:
            # English format: 1,299.90 -> remove ','
            try:
                vals.append(float(token.replace(",", "")))
            except ValueError:
                pass
        return vals

    # 3. Only comma present (e.g. 1299,90 or 150,00)
    if "," in token:
        try:
            vals.append(float(token.replace(",", ".")))
        except ValueError:
            pass
        return vals

    # 4. Only dot present (e.g. 1299.90 or 1.299)
    if "." in token:
        try:
            vals.append(float(token))
        except ValueError:
            pass
        # Could also be thousands separator (e.g. 1.299)
        parts = token.split(".")
        if len(parts) == 2 and len(parts[1]) == 3:
            try:
                vals.append(float(token.replace(".", "")))
            except ValueError:
                pass
        return vals

    return vals


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

    # Find full number tokens (including separators like 1.299,90 or 150.00 or 12345)
    reply_tokens = re.findall(r"\d+(?:[.,]\d+)*", reply)
    if not reply_tokens:
        return issues

    if not tools_called:
        issues.append("Araç çağırmadan sayısal bilgi verildi.")
        return issues

    corpus = " ".join(tool_results)
    tool_raw_tokens = re.findall(r"\d+(?:[.,]\d+)*", corpus)

    # Collect all numeric values and raw digit representations from tool results
    tool_numeric_values: list[float] = []
    tool_digit_sequences: set[str] = set()

    for ttok in tool_raw_tokens:
        for fval in _parse_candidate_floats(ttok):
            tool_numeric_values.append(fval)
        raw_digits = re.sub(r"\D", "", ttok)
        if raw_digits:
            tool_digit_sequences.add(raw_digits)

    # Also capture simple \d+ components from corpus
    tool_simple_digits = set(re.findall(r"\d+", corpus))

    def is_grounded(tok: str) -> bool:
        # Check numeric equality first
        tok_floats = _parse_candidate_floats(tok)
        for cand in tok_floats:
            for t_val in tool_numeric_values:
                if math.isclose(cand, t_val, rel_tol=1e-5, abs_tol=1e-3):
                    return True

        # Check raw digits match
        raw_digits = re.sub(r"\D", "", tok)
        if raw_digits and raw_digits in tool_digit_sequences:
            return True

        # Check simple components if tok is pure integer
        if tok.isdigit() and tok in tool_simple_digits:
            return True

        return False

    seen_violations: set[str] = set()
    for tok in reply_tokens:
        if not is_grounded(tok):
            if tok not in seen_violations:
                seen_violations.add(tok)
                issues.append(f"«{tok}» sayısı araç sonuçlarında geçmiyor.")

    return issues
