"""Grounding verification for agent responses against tool outputs.

Prevents numerical hallucinations (fake dates, amounts, days, order numbers)
by verifying that all numbers mentioned in the LLM response exist in tool results.
"""

import re


def check_reply_grounding(
    reply: str,
    tool_results: list[str],
    *,
    tools_called: bool,
) -> list[str]:
    """Verify that all numerical sequences in the response are grounded in tool results.

    Returns:
        list[str]: Detected grounding violations, empty if valid.
    """
    issues: list[str] = []
    reply_digits = set(re.findall(r"\d+", reply))

    if not reply_digits:
        return issues

    if not tools_called:
        issues.append("Araç çağırmadan sayısal bilgi verildi.")
        return issues

    corpus = " ".join(tool_results)
    tool_digits = set(re.findall(r"\d+", corpus))

    for num in sorted(reply_digits):
        if num not in tool_digits:
            issues.append(f"«{num}» sayısı araç sonuçlarında geçmiyor.")

    return issues
