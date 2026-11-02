import unicodedata
from app.rag.ingestion.models import QualityReport

MAX_EMPTY_PAGE_RATIO: float = 0.30  # Max 30% empty pages allowed
MAX_SUSPECT_CHAR_RATIO: float = 0.02  # Max 2% corrupt characters allowed


def calculate_suspect_char_ratio(text: str) -> float:
    """Calculates the ratio of suspect/corrupt characters in the text.

    Suspect characters include Unicode replacement character (\ufffd)
    and non-whitespace control characters.
    """
    if not text:
        return 0.0

    suspect_count = 0
    for char in text:
        # Check for unicode replacement character (\ufffd)
        if char == "\ufffd":
            suspect_count += 1
            continue

        # Check for control characters (exclude whitespace control characters \n, \r, \t)
        if char not in ("\n", "\r", "\t") and unicodedata.category(char).startswith("C"):
            suspect_count += 1

    return round(suspect_count / len(text), 4)


def build_report(
    page_count: int,
    empty_pages: list[int],
    full_text: str,
) -> QualityReport:
    """Evaluates document quality metrics and builds a QualityReport.

    Quarantines documents if empty page ratio exceeds 30% or suspect character
    ratio exceeds 2%.

    Args:
        page_count: Total number of pages in document.
        empty_pages: List of 1-based page indices identified as empty.
        full_text: Concatenated text content of the entire document.

    Returns:
        A QualityReport instance with status 'ok' or 'quarantine'.
    """
    reasons: list[str] = []
    suspect_ratio = calculate_suspect_char_ratio(full_text)

    # 1. Check empty pages ratio
    if page_count > 0:
        empty_ratio = len(empty_pages) / page_count
        if empty_ratio > MAX_EMPTY_PAGE_RATIO:
            reasons.append("too_many_empty_pages")
    elif page_count == 0:
        reasons.append("too_many_empty_pages")

    # 2. Check corrupt/garbled text ratio
    if suspect_ratio > MAX_SUSPECT_CHAR_RATIO:
        reasons.append("garbled_text")

    status = "quarantine" if reasons else "ok"

    return QualityReport(
        page_count=page_count,
        empty_pages=empty_pages,
        suspect_char_ratio=suspect_ratio,
        status=status,
        reasons=reasons,
    )
