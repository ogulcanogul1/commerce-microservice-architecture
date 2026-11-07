from collections.abc import Sequence
from app.rag.chunking.models import Chunk, ChunkStrategy
from app.rag.chunking.tokenizer import TiktokenTokenizer
from app.rag.evaluation.chunking.dataset import GoldenQuestion
from app.rag.evaluation.chunking.retrieval import Retriever, evaluate_retrieval
from app.rag.rerank.fake import FakeReranker
from app.rag.rerank.retriever import RerankingRetriever


class DummyRetriever(Retriever):
    def __init__(self, chunks: Sequence[Chunk]) -> None:
        self._chunks = list(chunks)
        self.last_search_k: int | None = None

    def index(self, chunks: Sequence[Chunk]) -> None:
        self._chunks = list(chunks)

    def search(self, query: str, k: int = 5) -> list[Chunk]:
        self.last_search_k = k
        return self._chunks[:k]

    def search_by_budget(self, query: str, budget: int, tokenizer: TiktokenTokenizer) -> list[Chunk]:
        return self._chunks[:2]


def _make_chunk(chunk_id: str, text: str) -> Chunk:
    return Chunk(
        id=chunk_id,
        strategy=ChunkStrategy.STRUCTURE,
        source_file="doc1.pdf",
        chunk_index=0,
        text=text,
        page_start=1,
        page_end=1,
        char_start=0,
        char_end=len(text),
        token_count=len(text.split()),
    )


def test_reranking_retriever_search():
    c0 = _make_chunk("c0", "elma armut")
    c1 = _make_chunk("c1", "kiraz çilek")
    c2 = _make_chunk("c2", "karpuz kavun")

    dummy = DummyRetriever([c0, c1, c2])
    # c1'e en yüksek skoru verelim
    reranker = FakeReranker(scores=[0.1, 0.9, 0.5])
    reranking_retriever = RerankingRetriever(dummy, reranker, candidates=10)

    results = reranking_retriever.search("meyveler", k=2)

    # İç retriever candidates (10) ile çağrılmış olmalı
    assert dummy.last_search_k == 10
    assert len(results) == 2
    # c1 en yüksek skorlu olduğu için ilk sırada çıkmalı
    assert results[0].id == "c1"
    assert results[1].id == "c2"

    assert reranking_retriever.last_rerank_ms >= 0.0
    assert len(reranking_retriever.total_rerank_ms) == 1


def test_reranking_retriever_search_by_budget():
    tokenizer = TiktokenTokenizer()
    c0 = _make_chunk("c0", "kısa metin bir iki")
    c1 = _make_chunk("c1", "daha uzun ve önemli metin kelimeleri")
    c2 = _make_chunk("c2", "üçüncü metin parçası")

    dummy = DummyRetriever([c0, c1, c2])
    reranker = FakeReranker(scores=[0.1, 0.9, 0.5])
    reranking_retriever = RerankingRetriever(dummy, reranker, candidates=10)

    # bütçe sadece 1-2 chunk sığdırabilecek kadar olsun
    selected = reranking_retriever.search_by_budget("sorgu", budget=20, tokenizer=tokenizer)
    assert dummy.last_search_k == 10
    assert len(selected) >= 1
    # İlk seçilen chunk en yüksek rerank skorlu c1 olmalı
    assert selected[0].id == "c1"


def test_reranking_retriever_eval_integration():
    c0 = _make_chunk("c0", "Sipariş teslimatı 3 iş günüdür.")
    c1 = _make_chunk("c1", "İade süresi 14 gündür.")

    dummy = DummyRetriever([c0, c1])
    # Kelime örtüşmesiyle c1 öne çıksın
    reranker = FakeReranker()
    reranking_retriever = RerankingRetriever(dummy, reranker, candidates=5)

    question = GoldenQuestion(
        id="Q01",
        question="İade süresi ne kadardır?",
        doc="doc1.pdf",
        evidence=["İade süresi 14 gündür."],
        category="single_fact",
    )

    summary, q_results = evaluate_retrieval(
        retriever=reranking_retriever,
        questions=[question],
        all_chunks=[c0, c1],
    )

    assert summary.total_questions == 1
    assert summary.hit_at_1 == 1.0
    assert summary.mrr == 1.0
    assert q_results[0].hit_at_1 is True
