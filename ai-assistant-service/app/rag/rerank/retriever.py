import time
from collections.abc import Sequence
from app.rag.chunking.models import Chunk
from app.rag.chunking.tokenizer import Tokenizer
from app.rag.evaluation.chunking.retrieval import Retriever, select_chunks_by_budget
from app.rag.rerank.base import Reranker


class RerankingRetriever(Retriever):
    """Mevcut Retriever protokolünü uygulayan sınıfları Reranker ile sarmalayan adaptör (Decorator).

    Özellikler:
    - Eval sürecinde fail-closed çalışır; rerank hatasında sessizce yutmaz, fırlatır.
    - search() metodunda iç retriever'dan max(candidates, k) aday çeker, reranker ile sıralayıp ilk k'yı döner.
    - search_by_budget() metodunda adayları yeniden sıralayıp select_chunks_by_budget uygular.
    - Gecikme ölçümleri için last_rerank_ms ve total_rerank_ms listesini tutar.
    """

    def __init__(
        self,
        inner: Retriever,
        reranker: Reranker,
        candidates: int = 20,
    ) -> None:
        self.inner = inner
        self.reranker = reranker
        self.candidates = candidates
        self.last_rerank_ms: float = 0.0
        self.total_rerank_ms: list[float] = []

    def index(self, chunks: Sequence[Chunk]) -> None:
        self.inner.index(chunks)

    def search(self, query: str, k: int = 5) -> list[Chunk]:
        k_search = max(self.candidates, k)
        candidate_chunks = self.inner.search(query, k=k_search)
        if not candidate_chunks:
            return []

        t0 = time.perf_counter()
        docs = [c.embedding_text for c in candidate_chunks]
        results = self.reranker.rerank(query, docs)
        ms = (time.perf_counter() - t0) * 1000.0
        self.last_rerank_ms = ms
        self.total_rerank_ms.append(ms)

        ranked = [candidate_chunks[r.index] for r in results]
        return ranked[:k]

    def search_by_budget(
        self, query: str, budget: int, tokenizer: Tokenizer
    ) -> list[Chunk]:
        candidate_chunks = self.inner.search(query, k=self.candidates)
        if not candidate_chunks:
            return []

        t0 = time.perf_counter()
        docs = [c.embedding_text for c in candidate_chunks]
        results = self.reranker.rerank(query, docs)
        ms = (time.perf_counter() - t0) * 1000.0
        self.last_rerank_ms = ms
        self.total_rerank_ms.append(ms)

        ranked = [candidate_chunks[r.index] for r in results]
        return select_chunks_by_budget(ranked, budget, tokenizer)
