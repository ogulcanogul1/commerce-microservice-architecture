import re
import unicodedata
from collections import Counter


def dehyphenate(text: str) -> str:
    """Merges words broken across lines by a hyphen while preserving hyphenated words.

    Example:
        'karşı-\\nlanır' -> 'karşılanır'
        'e-ticaret' -> 'e-ticaret'
    """
    pattern = r"([^\W\d_])-\s*[\r\n]+\s*([^\W\d_])"
    return re.sub(pattern, r"\1\2", text)


def normalize(text: str) -> str:
    """Normalizes Unicode text to NFC format and collapses multiple blank lines."""
    normalized = unicodedata.normalize("NFC", text)
    # Collapse 3 or more consecutive newlines into 2 (standard Markdown paragraph spacing)
    collapsed = re.sub(r"\n{3,}", "\n\n", normalized)
    return collapsed.strip()


def remove_repeated_lines(pages: list[str], margin_lines: int = 3) -> list[str]:
    """Detects and removes repeating headers and footers strictly at page margins.

    Crucial Invariants:
    1. Margin Scoping: Only the first `margin_lines` (headers) and last `margin_lines` (footers)
       of each page are examined for repetition. Body text in the middle is NEVER removed,
       even if repeated across pages (e.g. repeated notices or disclaimers).
    2. Table Exemption: Markdown table rows and separators (|) are never removed.
    3. Digits Masking: Numbers are masked to '#' so 'Page 1' and 'Page 2' match 'Page #'.

    Args:
        pages: List of raw page text strings.
        margin_lines: Number of lines at page top and bottom considered margins (default 3).

    Returns:
        Cleaned list of page text strings with headers/footers removed from margins.
    """
    if len(pages) < 2:
        return pages

    threshold = max(2, int(0.6 * len(pages)))

    def is_table_line(line: str) -> bool:
        return line.strip().startswith("|")

    def line_pattern(line: str) -> str:
        return re.sub(r"\d+", "#", line.strip())

    def get_margin_indices(total_lines: int) -> tuple[set[int], set[int]]:
        """Returns sets of line indices belonging to (top_margin, bottom_margin)."""
        if total_lines <= margin_lines * 2:
            # For very short pages, only the very first and very last non-empty lines can be margins
            top_set = {0} if total_lines > 0 else set()
            bot_set = {total_lines - 1} if total_lines > 1 else set()
            return top_set, bot_set
        top_set = set(range(margin_lines))
        bot_set = set(range(total_lines - margin_lines, total_lines))
        return top_set, bot_set

    # Step 1: Count pattern occurrences ONLY in page margins
    pattern_page_counts: Counter[str] = Counter()
    for page_text in pages:
        lines = page_text.splitlines()
        top_idx, bot_idx = get_margin_indices(len(lines))
        margin_indices = top_idx | bot_idx

        seen_in_this_page: set[str] = set()
        for idx in margin_indices:
            line = lines[idx].strip()
            if not line or is_table_line(line):
                continue
            pattern = line_pattern(line)
            seen_in_this_page.add(pattern)

        for pattern in seen_in_this_page:
            pattern_page_counts[pattern] += 1

    # Step 2: Identify recurring patterns that meet the threshold
    repeated_patterns = {
        pattern
        for pattern, count in pattern_page_counts.items()
        if count >= threshold
    }

    # Step 3: Remove repeated patterns ONLY from margins (body lines remain untouched)
    cleaned_pages: list[str] = []
    for page_text in pages:
        lines = page_text.splitlines()
        top_idx, bot_idx = get_margin_indices(len(lines))
        margin_indices = top_idx | bot_idx

        retained_lines: list[str] = []
        for idx, line in enumerate(lines):
            clean = line.strip()
            # If line is in margins and matches a repeated pattern (and is not table), drop it
            if idx in margin_indices and not is_table_line(clean):
                pattern = line_pattern(clean)
                if pattern in repeated_patterns:
                    continue
            retained_lines.append(line)

        cleaned_pages.append("\n".join(retained_lines))

    return cleaned_pages
