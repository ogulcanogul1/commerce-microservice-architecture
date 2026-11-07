import re
import time
from collections.abc import Sequence
from app.rag.evaluation.chunking.dataset import normalize_for_match
from app.rag.rerank.base import Reranker
from app.rag.rerank.models import RerankError, RerankResult, validate_rerank_results


class FakeReranker(Reranker):
    """Testler ve duman (smoke) koşuları için deterministik sahte reranker."""

    def __init__(
        self,
        scores: Sequence[float] | None = None,
        raise_on_call: Exception | None = None,
        delay_sec: float = 0.0,
        model_id: str = "fake-reranker",
    ) -> None:
        self.scores = list(scores) if scores is not None else None
        self.raise_on_call = raise_on_call
        self.delay_sec = delay_sec
        self.model_id = model_id
        self.calls: list[dict] = []

    def rerank(self, query: str, documents: Sequence[str]) -> list[RerankResult]:
        if self.delay_sec > 0:
            time.sleep(self.delay_sec)

        docs_list = list(documents)
        self.calls.append({"query": query, "documents": docs_list})

        if self.raise_on_call is not None:
            if isinstance(self.raise_on_call, RerankError):
                raise self.raise_on_call
            raise RerankError(f"Fake rerank failure: {self.raise_on_call}") from self.raise_on_call

        n = len(docs_list)
        if n == 0:
            return []

        # 1. Skorları belirle
        raw_scores: list[float] = []
        if self.scores is not None:
            if len(self.scores) != n:
                raise RerankError(
                    f"FakeReranker scores uzunluğu ({len(self.scores)}) doküman sayısıyla ({n}) eşleşmiyor"
                )
            raw_scores = list(self.scores)
        else:
            # Deterministik kelime örtüşmesi
            norm_query = normalize_for_match(query)
            query_words = set(re.findall(r"\w+", norm_query))
            for doc in docs_list:
                if not query_words:
                    raw_scores.append(0.0)
                    continue
                norm_doc = normalize_for_match(doc)
                doc_words = set(re.findall(r"\w+", norm_doc))
                overlap = len(query_words.intersection(doc_words))
                raw_scores.append(overlap / len(query_words))

        # 2. RerankResult nesnelerini oluştur
        results = [RerankResult(index=i, score=raw_scores[i]) for i in range(n)]

        # 3. Kararlı sıralama: Skora göre azalan; eşitlikte orijinal index'e göre artan
        sorted_results = sorted(results, key=lambda r: (-r.score, r.index))

        # 4. Doğrulama
        validate_rerank_results(sorted_results, n)
        return sorted_results
