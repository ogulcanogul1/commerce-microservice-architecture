"""Validation of chunk token lengths against embedding model context window limits."""

from typing import Sequence
from pydantic import BaseModel, Field

from app.rag.chunking.models import Chunk
from app.rag.chunking.tokenizer import TiktokenTokenizer, Tokenizer
from app.rag.embedding.base import Embedder


class ChunkFitReport(BaseModel):
    """Validation report detailing whether chunks fit within an embedder's token limits."""

    total_chunks: int
    max_input_tokens: int
    max_chunk_tokens: int
    avg_chunk_tokens: float
    oversized_chunks: list[tuple[str, int]] = Field(
        default_factory=list,
        description="List of (chunk_id, token_count) tuples that exceed the max_input_tokens limit",
    )
    all_fit: bool


class EmbedderTokenizerAdapter:
    """Adapts an Embedder's count_tokens method to the Tokenizer protocol."""

    def __init__(self, embedder: Embedder) -> None:
        self.embedder = embedder

    def count(self, text: str) -> int:
        return self.embedder.count_tokens(text)

    def token_spans(self, text: str) -> list[tuple[int, int]]:
        return []


def validate_chunks_fit(
    chunks: Sequence[Chunk],
    embedder: Embedder,
    tokenizer: Tokenizer | None = None,
) -> ChunkFitReport:
    """Validate that every chunk's embedding_text fits within the embedder's max_input_tokens.

    Defaults to the embedder's own tokenizer (via EmbedderTokenizerAdapter).
    Returns a ChunkFitReport containing statistics and any violating chunks.
    """
    if not chunks:
        return ChunkFitReport(
            total_chunks=0,
            max_input_tokens=embedder.max_input_tokens,
            max_chunk_tokens=0,
            avg_chunk_tokens=0.0,
            oversized_chunks=[],
            all_fit=True,
        )

    tok = tokenizer if tokenizer is not None else EmbedderTokenizerAdapter(embedder)

    counts = [tok.count(c.embedding_text) for c in chunks]
    oversized: list[tuple[str, int]] = []

    for chunk, token_count in zip(chunks, counts):
        if token_count > embedder.max_input_tokens:
            oversized.append((chunk.id, token_count))

    total = len(chunks)
    max_tokens = max(counts) if counts else 0
    avg_tokens = round(sum(counts) / total, 2) if total > 0 else 0.0

    return ChunkFitReport(
        total_chunks=total,
        max_input_tokens=embedder.max_input_tokens,
        max_chunk_tokens=max_tokens,
        avg_chunk_tokens=avg_tokens,
        oversized_chunks=oversized,
        all_fit=len(oversized) == 0,
    )


def compute_token_divergence_ratio(
    texts: Sequence[str],
    base_tokenizer: Tokenizer,
    model_tokenizer: Tokenizer,
) -> float:
    """Compute the divergence ratio: (base_tokenizer count) / (model_tokenizer count).

    Helps detect token inflation/deflation (especially in non-English text) between tokenizers.
    """
    if not texts:
        return 1.0

    base_sum = sum(base_tokenizer.count(t) for t in texts)
    model_sum = sum(model_tokenizer.count(t) for t in texts)

    if model_sum == 0:
        return 1.0

    return round(base_sum / model_sum, 4)
