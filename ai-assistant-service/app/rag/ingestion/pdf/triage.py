from pathlib import Path
import pymupdf


def page_char_counts(path: Path | str) -> list[int]:
    """Inspects a PDF and returns the stripped character count for each page.

    Args:
        path: Path to the target PDF file.

    Returns:
        A list of integer character counts corresponding to each page.
    """
    doc: pymupdf.Document = pymupdf.open(str(path))
    counts: list[int] = []

    try:
        for page in doc:
            text = page.get_text().strip()
            counts.append(len(text))
    finally:
        doc.close()

    return counts


def find_empty_pages(counts: list[int], min_chars: int = 50) -> list[int]:
    """Identifies pages that contain fewer characters than the minimum threshold.

    Args:
        counts: List of character counts per page.
        min_chars: Minimum character threshold below which a page is considered empty.

    Returns:
        A list of 1-based page numbers considered empty.
    """
    return [page_idx + 1 for page_idx, count in enumerate(counts) if count < min_chars]
