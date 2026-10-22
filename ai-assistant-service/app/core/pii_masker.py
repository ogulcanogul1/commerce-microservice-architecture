import re
from dataclasses import dataclass, field

# 1. Turkish IBAN: TR followed by 24 digits (with optional spaces)
_IBAN_PATTERN = re.compile(
    r"\bTR\d{2}(?:\s?\d{4}){5}\s?\d{2}\b",
    re.IGNORECASE,
)

# 2. Credit Card: 16 digits grouped by 4 (with spaces or hyphens) or contiguous 16 digits
_CREDIT_CARD_PATTERN = re.compile(
    r"\b(?:\d{4}[-\s]){3}\d{4}\b|\b\d{16}\b"
)

# 3. Turkish National ID (TCKN): 11 digits starting with 1-9
_TCKN_PATTERN = re.compile(
    r"\b[1-9]\d{10}\b"
)

# 4. Explicit password / PIN / CVV disclosures
_SECRET_KV_PATTERN = re.compile(
    r"(?i)\b(şifre(?:m)?|parola(?:m)?|password|pin|cvv|cvc)\s*[:=]\s*(\S+)"
)


@dataclass(frozen=True)
class PIIMaskResult:
    masked_text: str
    was_masked: bool = False
    detected_types: list[str] = field(default_factory=list)


class PIIMasker:
    """
    Scans and masks sensitive Personally Identifiable Information (PII)
    such as Credit Card numbers, Turkish National ID (TCKN), IBAN, and passwords
    before prompts are transmitted to external LLM providers.
    """

    @staticmethod
    def mask_text(text: str) -> PIIMaskResult:
        if not text:
            return PIIMaskResult(masked_text="", was_masked=False, detected_types=[])

        masked = text
        detected: list[str] = []

        if _IBAN_PATTERN.search(masked):
            masked = _IBAN_PATTERN.sub("[MASKED_IBAN]", masked)
            detected.append("IBAN")

        if _CREDIT_CARD_PATTERN.search(masked):
            masked = _CREDIT_CARD_PATTERN.sub("[MASKED_CARD]", masked)
            detected.append("CREDIT_CARD")

        if _TCKN_PATTERN.search(masked):
            masked = _TCKN_PATTERN.sub("[MASKED_TCKN]", masked)
            detected.append("TCKN")

        if _SECRET_KV_PATTERN.search(masked):
            masked = _SECRET_KV_PATTERN.sub(r"\1: [MASKED_SECRET]", masked)
            detected.append("SECRET")

        return PIIMaskResult(
            masked_text=masked,
            was_masked=len(detected) > 0,
            detected_types=detected,
        )
