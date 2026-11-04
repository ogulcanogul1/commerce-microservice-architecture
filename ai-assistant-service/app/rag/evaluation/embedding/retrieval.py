"""Dense and Hybrid (RRF) retrievers for embedding evaluation."""

from typing import Sequence
import numpy as np

from app.rag.chunking.models import Chunk
from app.rag.chunking.tokenizer import Tokenizer
from app.rag.embedding.base import Embedder
from app.rag.evaluation.chunking.retrieval import (
    BM25Retriever,
    Retriever,
    select_chunks_by_budget,
)


class DenseRetriever:
    """In-memory dense retriever using dot product (cosine similarity) on L2-normalized vectors."""

    def __init__(self, embedder: Embedder) -> None:
        self.embedder = embedder
        self.chunks: list[Chunk] = []
        self.matrix: np.ndarray | None = None

    def index(self, chunks: Sequence[Chunk]) -> None:
        """Embed chunks using their embedding_text and store matrix in memory."""
        self.chunks = list(chunks)
        if not self.chunks:
            self.matrix = None
            return

        texts = [c.embedding_text for c in self.chunks]
        self.matrix = self.embedder.embed_documents(texts)

    def search(self, query: str, k: int = 5) -> list[Chunk]:
        """Search top-k chunks by cosine similarity with deterministic tie-breaking."""
        if not self.chunks or self.matrix is None or not query.strip():
            return []

        q_vec = self.embedder.embed_query(query)
        scores = self.matrix @ q_vec

        # Deterministic sorting: highest score first, ties broken by corpus index
        ranked_indices = sorted(
            range(len(scores)),
            key=lambda i: (-float(scores[i]), i),
        )
        top_indices = ranked_indices[:k]
        return [self.chunks[i] for i in top_indices]

    def search_by_budget(
        self, query: str, budget: int, tokenizer: Tokenizer
    ) -> list[Chunk]:
        """Accumulate ranked chunks up to a strict token budget."""
        if not self.chunks or self.matrix is None or not query.strip() or budget <= 0:
            return []

        ranked = self.search(query, k=len(self.chunks))
        return select_chunks_by_budget(ranked, budget, tokenizer)


class HybridRetriever:
    """Hybrid retriever combining Dense and BM25 search via Reciprocal Rank Fusion (RRF)."""

    def __init__(
        self,
        dense: DenseRetriever,
        bm25: BM25Retriever,
        k_rrf: int = 60,
    ) -> None:
        self.dense = dense
        self.bm25 = bm25
        self.k_rrf = k_rrf
        self.chunks: list[Chunk] = []

    def index(self, chunks: Sequence[Chunk]) -> None:
        """Index both Dense and BM25 retrievers with the given chunks."""
        self.chunks = list(chunks)
        self.dense.index(self.chunks)
        self.bm25.index(self.chunks)

    def search(self, query: str, k: int = 5) -> list[Chunk]:
        """Search top-k chunks by combining dense and lexical ranks using RRF.

        RRF score = sum(1.0 / (k_rrf + rank_m)) for each ranking method m.
        """
        if not self.chunks or not query.strip():
            return []

        n = len(self.chunks)
        dense_results = self.dense.search(query, k=n)
        bm25_results = self.bm25.search(query, k=n)

        # RRF skor tablosu
        rrf_scores: dict[str, float] = {c.id: 0.0 for c in self.chunks}
        chunk_map = {c.id: c for c in self.chunks}
        index_order = {c.id: i for i, c in enumerate(self.chunks)}

        for rank, c in enumerate(dense_results, start=1):
            rrf_scores[c.id] += 1.0 / (self.k_rrf + rank)

        for rank, c in enumerate(bm25_results, start=1):
            rrf_scores[c.id] += 1.0 / (self.k_rrf + rank)

        # Deterministik sıralama: yüksek RRF skoru ilk, eşitlikte korpus sırası
        sorted_ids = sorted(
            rrf_scores.keys(),
            key=lambda cid: (-rrf_scores[cid], index_order[cid]),
        )
        return [chunk_map[cid] for cid in sorted_ids[:k]]

    def search_by_budget(
        self, query: str, budget: int, tokenizer: Tokenizer
    ) -> list[Chunk]:
        """Accumulate RRF-ranked chunks up to a strict token budget."""
        if not self.chunks or not query.strip() or budget <= 0:
            return []

        ranked = self.search(query, k=len(self.chunks))
        return select_chunks_by_budget(ranked, budget, tokenizer)
