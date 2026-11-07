"""Personally Identifiable Information (PII) masking utilities.

Detects and masks sensitive user data (TCKN, Credit Cards, IBAN, Phone numbers,
and Emails) before sending queries to external LLM providers or embedding APIs.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class _PIISpan:
    start: int
    end: int
    pii_type: str
    placeholder: str


def validate_tckn_checksum(value: str) -> bool:
    """Validate Turkish Republic Citizen ID (TCKN) using official 10th and 11th digit checksums.

    Rules:
    - 11 numeric digits.
    - First digit cannot be '0'.
    - 10th digit = ((d1 + d3 + d5 + d7 + d9) * 7 - (d2 + d4 + d6 + d8)) % 10
    - 11th digit = sum(d1..d10) % 10
    """
    if len(value) != 11 or not value.isdigit() or value[0] == "0":
        return False

    digits = [int(c) for c in value]

    d10 = ((sum(digits[0:9:2]) * 7) - sum(digits[1:8:2])) % 10
    if digits[9] != d10:
        return False

    d11 = sum(digits[0:10]) % 10
    return digits[10] == d11


def validate_luhn(number: str) -> bool:
    """Validate payment card number using the standard Luhn algorithm (mod 10).

    Rules:
    - 13 to 19 digits.
    - Doubling every second digit from right to left, subtracting 9 if > 9, sum % 10 == 0.
    """
    digits = [int(c) for c in number if c.isdigit()]
    if not (13 <= len(digits) <= 19):
        return False

    checksum = 0
    reverse_digits = digits[::-1]
    for i, d in enumerate(reverse_digits):
        if i % 2 == 1:
            d = d * 2
            if d > 9:
                d -= 9
        checksum += d

    return checksum % 10 == 0


# Pre-compiled Regex patterns
_IBAN_PATTERN = re.compile(r"\bTR\s*(?:\d\s*){23}\d\b", re.IGNORECASE)
_EMAIL_PATTERN = re.compile(
    r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"
)
_PHONE_PATTERN = re.compile(
    r"(?<!\w)(?:\+90[\s.-]*|0[\s.-]*)5\d{2}[\s.-]*\d{3}[\s.-]*\d{2}[\s.-]*\d{2}(?!\d)"
)
_CARD_CANDIDATE_PATTERN = re.compile(r"(?<!\d)(?:\d[\s-]*){12,18}\d(?!\d)")
_TCKN_CANDIDATE_PATTERN = re.compile(r"(?<!\d)[1-9]\d{10}(?!\d)")


def _overlaps(start: int, end: int, accepted: list[_PIISpan]) -> bool:
    return any(not (end <= span.start or start >= span.end) for span in accepted)


def mask_pii(text: str) -> tuple[str, list[str]]:
    """Mask sensitive PII entities in the given text while leaving business identifiers intact.

    Returns:
        tuple[str, list[str]]: (masked_text, list_of_detected_pii_types_in_order)
    """
    if not text:
        return text, []

    spans: list[_PIISpan] = []

    # 1. IBAN
    for match in _IBAN_PATTERN.finditer(text):
        s, e = match.span()
        if not _overlaps(s, e, spans):
            spans.append(_PIISpan(start=s, end=e, pii_type="iban", placeholder="[IBAN]"))

    # 2. Email
    for match in _EMAIL_PATTERN.finditer(text):
        s, e = match.span()
        if not _overlaps(s, e, spans):
            spans.append(_PIISpan(start=s, end=e, pii_type="email", placeholder="[EPOSTA]"))

    # 3. Card (Luhn check required)
    for match in _CARD_CANDIDATE_PATTERN.finditer(text):
        s, e = match.span()
        raw_digits = re.sub(r"[\s-]", "", match.group(0))
        if validate_luhn(raw_digits) and not _overlaps(s, e, spans):
            spans.append(_PIISpan(start=s, end=e, pii_type="card", placeholder="[KART]"))

    # 4. Phone
    for match in _PHONE_PATTERN.finditer(text):
        s, e = match.span()
        if not _overlaps(s, e, spans):
            spans.append(_PIISpan(start=s, end=e, pii_type="phone", placeholder="[TELEFON]"))

    # 5. TCKN (Checksum check required)
    for match in _TCKN_CANDIDATE_PATTERN.finditer(text):
        s, e = match.span()
        if validate_tckn_checksum(match.group(0)) and not _overlaps(s, e, spans):
            spans.append(_PIISpan(start=s, end=e, pii_type="tckn", placeholder="[TCKN]"))

    if not spans:
        return text, []

    # Sort spans by start index to maintain original appearance order for detected_types
    spans_by_appearance = sorted(spans, key=lambda s: s.start)
    detected_types = list(dict.fromkeys(s.pii_type for s in spans_by_appearance))

    # Replace from right to left to avoid altering string character offsets
    result = text
    for span in sorted(spans, key=lambda s: s.start, reverse=True):
        result = result[: span.start] + span.placeholder + result[span.end :]

    return result, detected_types
