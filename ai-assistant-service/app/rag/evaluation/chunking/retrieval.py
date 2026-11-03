import re
from typing import Optional, Protocol, Sequence, runtime_checkable
from pydantic import BaseModel, Field
from rank_bm25 import BM25Okapi

from app.rag.chunking.models import Chunk
from app.rag.chunking.tokenizer import Tokenizer
from app.rag.evaluation.chunking.dataset import GoldenQuestion, normalize_for_match


@runtime_checkable
class Retriever(Protocol):
    """Protocol defining the search interface for evaluation."""

    def index(self, chunks: Sequence[Chunk]) -> None:
        """Index chunks for retrieval."""
        ...

    def search(self, query: str, k: int = 5) -> list[Chunk]:
        """Search and return the top-k chunks."""
        ...

    def search_by_budget(
        self, query: str, budget: int, tokenizer: Tokenizer
    ) -> list[Chunk]:
        """Search and return chunks accumulated up to a strict token budget."""
        ...


class BM25Retriever:
    """In-memory lexical retriever using BM25Okapi with Turkish-aware tokenization."""

    def __init__(self, use_stemming: bool = False) -> None:
        self.use_stemming = use_stemming
        self.chunks: list[Chunk] = []
        self.bm25: Optional[BM25Okapi] = None

    def _tokenize(self, text: str) -> list[str]:
        """Tokenize text into words with Turkish normalization and optional 5-char prefix-stem."""
        norm = normalize_for_match(text)
        words = re.findall(r"\w+", norm)
        if self.use_stemming:
            # Basit Türkçe prefix-stem: 5 karakterden uzun kelimelerin ilk 5 karakterini al
            return [w[:5] if len(w) > 5 else w for w in words]
        return words

    def index(self, chunks: Sequence[Chunk]) -> None:
        self.chunks = list(chunks)
        if not self.chunks:
            self.bm25 = None
            return

        # İndeksleme için embedding_text kullanılır (breadcrumb ablation için)
        tokenized_corpus = [self._tokenize(c.embedding_text) for c in self.chunks]
        self.bm25 = BM25Okapi(tokenized_corpus)

    def search(self, query: str, k: int = 5) -> list[Chunk]:
        if not self.chunks or self.bm25 is None or not query.strip():
            return []

        q_tokens = self._tokenize(query)
        if not q_tokens:
            return self.chunks[:k]

        scores = self.bm25.get_scores(q_tokens)
        ranked_indices = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)
        top_indices = ranked_indices[:k]
        return [self.chunks[i] for i in top_indices]

    def search_by_budget(
        self, query: str, budget: int, tokenizer: Tokenizer
    ) -> list[Chunk]:
        """Return chunks ranked by score until cumulative token count reaches budget."""
        if not self.chunks or self.bm25 is None or not query.strip() or budget <= 0:
            return []

        q_tokens = self._tokenize(query)
        scores = self.bm25.get_scores(q_tokens)
        ranked_indices = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)

        selected: list[Chunk] = []
        accumulated_tokens = 0

        for idx in ranked_indices:
            chunk = self.chunks[idx]
            c_tokens = tokenizer.count(chunk.text)
            if accumulated_tokens + c_tokens <= budget or not selected:
                selected.append(chunk)
                accumulated_tokens += c_tokens
            else:
                break

        return selected


class QuestionResult(BaseModel):
    """Evaluation result for a single GoldenQuestion."""
    question_id: str
    category: str
    evidence_intact: bool = Field(
        description="Whether the complete evidence exists intact in at least one chunk"
    )
    evidence_fragmented: bool = Field(
        description="Whether the evidence is fragmented across chunks and nowhere complete"
    )
    hit_at_1: bool
    hit_at_3: bool
    hit_at_5: bool
    mrr: float = Field(ge=0.0, le=1.0, description="Reciprocal rank of first correct chunk")


class RetrievalEvalSummary(BaseModel):
    """Aggregated retrieval metrics across questions and categories."""
    total_questions: int
    evidence_intact_ratio: float = Field(ge=0.0, le=1.0)
    evidence_fragmented_ratio: float = Field(ge=0.0, le=1.0)
    hit_at_1: float = Field(ge=0.0, le=1.0)
    hit_at_3: float = Field(ge=0.0, le=1.0)
    hit_at_5: float = Field(ge=0.0, le=1.0)
    mrr: float = Field(ge=0.0, le=1.0)
    category_hit3: dict[str, float] = Field(
        default_factory=dict,
        description="Hit@3 breakdown by question category",
    )


def chunk_contains_evidence(chunk: Chunk, evidence: list[str]) -> bool:
    """Check if all parts of evidence are completely present within a single chunk."""
    norm_chunk = normalize_for_match(chunk.text)
    for part in evidence:
        norm_part = normalize_for_match(part)
        if norm_part not in norm_chunk:
            return False
    return True


def evaluate_retrieval(
    retriever: Retriever,
    questions: list[GoldenQuestion],
    all_chunks: list[Chunk],
    token_budget: Optional[int] = None,
    tokenizer: Optional[Tokenizer] = None,
) -> tuple[RetrievalEvalSummary, list[QuestionResult]]:
    """Evaluate retrieval performance of indexed chunks against golden questions."""
    retriever.index(all_chunks)
    results: list[QuestionResult] = []

    for q in questions:
        # 1. evidence_intact kontrolü (retrieval'dan bağımsız parçalama hasarı kontrolü)
        intact = any(chunk_contains_evidence(c, q.evidence) for c in all_chunks)
        fragmented = not intact

        # 2. Retrieval araması yap
        if token_budget is not None and tokenizer is not None:
            retrieved = retriever.search_by_budget(q.question, token_budget, tokenizer)
        else:
            retrieved = retriever.search(q.question, k=5)

        # 3. Hit@k ve MRR hesapla
        first_correct_rank: Optional[int] = None
        for rank, c in enumerate(retrieved, start=1):
            if chunk_contains_evidence(c, q.evidence):
                first_correct_rank = rank
                break

        hit1 = first_correct_rank == 1
        hit3 = first_correct_rank is not None and first_correct_rank <= 3
        hit5 = first_correct_rank is not None and first_correct_rank <= 5
        mrr = 1.0 / first_correct_rank if first_correct_rank is not None else 0.0

        results.append(
            QuestionResult(
                question_id=q.id,
                category=q.category,
                evidence_intact=intact,
                evidence_fragmented=fragmented,
                hit_at_1=hit1,
                hit_at_3=hit3,
                hit_at_5=hit5,
                mrr=round(mrr, 4),
            )
        )

    if not results:
        return (
            RetrievalEvalSummary(
                total_questions=0,
                evidence_intact_ratio=0.0,
                evidence_fragmented_ratio=0.0,
                hit_at_1=0.0,
                hit_at_3=0.0,
                hit_at_5=0.0,
                mrr=0.0,
                category_hit3={},
            ),
            [],
        )

    n = len(results)
    intact_ratio = round(sum(1 for r in results if r.evidence_intact) / n, 4)
    fragmented_ratio = round(sum(1 for r in results if r.evidence_fragmented) / n, 4)
    hit1_ratio = round(sum(1 for r in results if r.hit_at_1) / n, 4)
    hit3_ratio = round(sum(1 for r in results if r.hit_at_3) / n, 4)
    hit5_ratio = round(sum(1 for r in results if r.hit_at_5) / n, 4)
    avg_mrr = round(sum(r.mrr for r in results) / n, 4)

    # Kategori bazlı Hit@3 kırılımı
    cat_results: dict[str, list[QuestionResult]] = {}
    for r in results:
        cat_results.setdefault(r.category, []).append(r)

    category_hit3 = {}
    for cat, cat_list in sorted(cat_results.items()):
        category_hit3[cat] = round(sum(1 for r in cat_list if r.hit_at_3) / len(cat_list), 4)

    summary = RetrievalEvalSummary(
        total_questions=n,
        evidence_intact_ratio=intact_ratio,
        evidence_fragmented_ratio=fragmented_ratio,
        hit_at_1=hit1_ratio,
        hit_at_3=hit3_ratio,
        hit_at_5=hit5_ratio,
        mrr=avg_mrr,
        category_hit3=category_hit3,
    )

    return summary, results
