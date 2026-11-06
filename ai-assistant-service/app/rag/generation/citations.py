"""Citation extraction and grounding validation utilities."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from app.rag.evaluation.chunking.dataset import normalize_for_match
from app.rag.generation.models import ContextBlock, ValidationIssue

if TYPE_CHECKING:
    pass

# Common Turkish abbreviations that should not trigger sentence boundaries
ABBREVIATIONS: tuple[str, ...] = (
    "vb",
    "vs",
    "örn",
    "s",
    "md",
    "no",
    "dr",
    "prof",
)

_ABSTAIN_PATTERN = re.compile(r"\bbulunamadı\b")
_CITATION_PATTERN = re.compile(r"\[(\d+)\]")
_SENTENCE_SPLIT_PATTERN = re.compile(r"([.!?]+(?:\s*\[\d+\])*)(?=\s+|$)")


def split_sentences(text: str) -> list[str]:
    """Split natural text into discrete sentences while properly preserving trailing citations.

    Rules:
    - Sentence terminators: '.', '!', '?'.
    - Trailing citation markers immediately following punctuation (e.g. '14 gündür. [1]')
      are bound to the preceding sentence.
    - Decimals, dates, and common abbreviations (vb., vs., örn., s., Md., No.)
      do not cause sentence splits.
    - Markdown list items (starting with '-' or digits) are treated as distinct sentences.
    - Empty or whitespace-only segments are discarded.
    """
    if not text or not text.strip():
        return []

    lines = [line.strip() for line in text.splitlines() if line.strip()]
    sentences: list[str] = []

    for line in lines:
        pos = 0
        for match in _SENTENCE_SPLIT_PATTERN.finditer(line):
            punct_end = match.end()
            segment = line[pos:punct_end].strip()

            text_before = line[pos : match.start()].strip()
            last_word = text_before.split()[-1].lower() if text_before.split() else ""
            cleaned_last_word = last_word.rstrip(".!?,:;")

            # 1. Check abbreviation boundary
            if cleaned_last_word in ABBREVIATIONS:
                continue

            # 2. Check decimal / date boundary (e.g. 1.000 or 14.05.2026)
            if (
                match.start() > 0
                and punct_end < len(line)
                and line[match.start() - 1].isdigit()
                and line[punct_end : punct_end + 1].isdigit()
            ):
                continue

            if segment:
                sentences.append(segment)
            pos = punct_end

        if pos < len(line):
            remainder = line[pos:].strip()
            if remainder:
                sentences.append(remainder)

    return sentences


def extract_citation_numbers(sentence: str) -> list[int]:
    """Extract citation reference numbers from a sentence in appearance order, deduplicated."""
    matches = _CITATION_PATTERN.findall(sentence)
    seen: set[int] = set()
    result: list[int] = []
    for m in matches:
        val = int(m)
        if val not in seen:
            seen.add(val)
            result.append(val)
    return result


def cited_numbers(answer: str) -> list[int]:
    """Extract all distinct citation reference numbers from an entire answer."""
    return extract_citation_numbers(answer)


def is_abstain(answer: str) -> bool:
    """Determine whether the answer represents an explicit abstain / refusal.

    Returns True if the whole word 'bulunamadı' appears in the normalized answer text.
    Kelime sınırı zorunlu: "bulunamadığında" gibi meşru kelimeler abstain sayılmaz.
    """
    if not answer or not answer.strip():
        return False
    normalized = normalize_for_match(answer)
    return _ABSTAIN_PATTERN.search(normalized) is not None


def validate_answer(answer: str, blocks: list[ContextBlock]) -> list[ValidationIssue]:
    """Validate that the model's generated answer strictly satisfies grounding rules.

    Checks:
    1. uncited_sentence: Every sentence must contain at least one citation '[n]'.
    2. invalid_citation: Every citation '[n]' must refer to a valid block in 1..len(blocks).
    3. number_not_in_source: Every numeric token in a sentence must be present in the text/header
       of the sources cited by that sentence. (Skipped for sentences containing invalid citations).
    """
    if not answer or not answer.strip():
        return [ValidationIssue(type="empty_answer", sentence="", detail="")]

    sentences = split_sentences(answer)
    if not sentences:
        return [ValidationIssue(type="empty_answer", sentence="", detail="")]

    block_map = {b.number: b for b in blocks}
    max_block = len(blocks)
    issues: list[ValidationIssue] = []

    for sentence in sentences:
        cit_nums = extract_citation_numbers(sentence)

        # Check 1: Uncited sentence
        if not cit_nums:
            issues.append(
                ValidationIssue(
                    type="uncited_sentence",
                    sentence=sentence,
                    detail="",
                )
            )
            continue

        # Check 2: Invalid citation numbers
        invalid_cits = [n for n in cit_nums if n < 1 or n > max_block]
        for inv in invalid_cits:
            issues.append(
                ValidationIssue(
                    type="invalid_citation",
                    sentence=sentence,
                    detail=f"[{inv}]",
                )
            )

        # If invalid citations exist, skip number check for this sentence
        if invalid_cits:
            continue

        # Check 3: Numeric consistency with cited sources
        # Strip citation brackets first so "[1]" is not mistaken for the number 1
        sentence_clean = _CITATION_PATTERN.sub("", sentence)
        sentence_numbers = list(dict.fromkeys(re.findall(r"\d+", sentence_clean)))

        if sentence_numbers:
            # Aggregate all text and header content from cited blocks
            source_content = " ".join(
                f"{block_map[n].chunk.text} {block_map[n].header}"
                for n in cit_nums
                if n in block_map
            )
            source_numbers = set(re.findall(r"\d+", source_content))

            for num in sentence_numbers:
                if num not in source_numbers:
                    issues.append(
                        ValidationIssue(
                            type="number_not_in_source",
                            sentence=sentence,
                            detail=num,
                        )
                    )

    return issues
