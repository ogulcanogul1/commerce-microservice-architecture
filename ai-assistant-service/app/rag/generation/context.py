"""Context builder module for formatting retrieved search hits into numbered prompt blocks."""

from __future__ import annotations

import logging
import re
from collections.abc import Sequence

from app.rag.chunking.tokenizer import Tokenizer
from app.rag.generation.models import ContextBlock
from app.rag.vectorstore.models import SearchHit

logger = logging.getLogger(__name__)


def _escape_sources_tags(text: str) -> str:
    """Escape prompt delimiter tags to prevent indirect prompt injection from document text."""
    text = re.sub(r"</kaynaklar>", "‹/kaynaklar›", text, flags=re.IGNORECASE)
    text = re.sub(r"<kaynaklar>", "‹kaynaklar›", text, flags=re.IGNORECASE)
    return text


def _format_header(number: int, hit: SearchHit) -> str:
    """Format the citation reference header line for a context block."""
    chunk = hit.chunk
    if chunk.page_start == chunk.page_end:
        page_str = f"s. {chunk.page_start}"
    else:
        page_str = f"s. {chunk.page_start}–{chunk.page_end}"

    if chunk.heading_path:
        heading_str = f", {' > '.join(chunk.heading_path)}"
    else:
        heading_str = ""

    raw_header = f"[{number}] ({chunk.source_file}, {page_str}{heading_str})"
    return _escape_sources_tags(raw_header)


def build_context(
    hits: Sequence[SearchHit],
    *,
    tokenizer: Tokenizer,
    budget: int,
) -> list[ContextBlock]:
    """Select and format search hits into numbered ContextBlock objects adhering to token budget.

    Rules:
    - Order of hits is preserved.
    - Numbers start at 1 and increment continuously without gaps.
    - Chunks with duplicate IDs are deduplicated (first occurrence retained).
    - Cost per block = tokenizer.count(header) + tokenizer.count(text).
    - If the first block alone exceeds the budget, it is included anyway with a warning log.
    - Subsequent blocks are included as long as total tokens <= budget.
    - `<kaynaklar>` and `</kaynaklar>` tags in headers and text are escaped.
    """
    if not hits:
        return []

    blocks: list[ContextBlock] = []
    seen_chunk_ids: set[str] = set()
    total_tokens = 0

    for hit in hits:
        chunk = hit.chunk
        if chunk.id in seen_chunk_ids:
            continue
        seen_chunk_ids.add(chunk.id)

        next_number = len(blocks) + 1
        header = _format_header(next_number, hit)
        escaped_text = _escape_sources_tags(chunk.text)

        header_tokens = tokenizer.count(header)
        text_tokens = tokenizer.count(escaped_text)
        block_cost = header_tokens + text_tokens

        if not blocks:
            # First block is always included even if exceeding budget
            if block_cost > budget:
                logger.warning(
                    "First context block alone exceeds budget: %d > %d",
                    block_cost,
                    budget,
                )
            sanitized_chunk = chunk.model_copy(update={"text": escaped_text})
            blocks.append(
                ContextBlock(
                    number=next_number,
                    chunk=sanitized_chunk,
                    header=header,
                    token_count=block_cost,
                )
            )
            total_tokens += block_cost
        else:
            if total_tokens + block_cost <= budget:
                sanitized_chunk = chunk.model_copy(update={"text": escaped_text})
                blocks.append(
                    ContextBlock(
                        number=next_number,
                        chunk=sanitized_chunk,
                        header=header,
                        token_count=block_cost,
                    )
                )
                total_tokens += block_cost
            else:
                # Budget reached; remaining hits are excluded
                break

    return blocks
