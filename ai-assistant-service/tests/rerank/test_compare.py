from pathlib import Path
from qdrant_client import QdrantClient
from app.rag.chunking.models import Chunk, ChunkStrategy
from app.rag.embedding.fake import FakeEmbedder
from app.rag.evaluation.chunking.dataset import GoldenQuestion
from app.rag.evaluation.chunking.retrieval import Retriever
from app.rag.evaluation.rerank.compare import (
    CachedRetriever,
    classify_flips,
    compute_percentiles,
    first_correct_rank,
    run_comparison,
)
from app.rag.rerank.fake import FakeReranker


def _make_chunk(cid: str, text: str) -> Chunk:
    return Chunk(
        id=cid,
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


def test_first_correct_rank():
    c1 = _make_chunk("c1", "İade süresi 14 gündür.")
    c2 = _make_chunk("c2", "Kargo ücretsizdir.")
    c3 = _make_chunk("c3", "Müşteri hizmetleri haftanın 7 günü açıktır.")

    # 1. İlk dokümanda kanıt var
    assert first_correct_rank([c1, c2, c3], ["14 gündür"]) == 1

    # 2. Üçüncü dokümanda kanıt var
    assert first_correct_rank([c1, c2, c3], ["haftanın 7 günü"]) == 3

    # 3. Hiçbir dokümanda kanıt yok
    assert first_correct_rank([c1, c2, c3], ["garanti süresi 2 yıl"]) is None


def test_classify_flips():
    q1 = GoldenQuestion(id="Q1", question="Soru 1", doc="d.pdf", evidence=["ev1"], category="single_fact")
    q2 = GoldenQuestion(id="Q2", question="Soru 2", doc="d.pdf", evidence=["ev2"], category="single_fact")
    q3 = GoldenQuestion(id="Q3", question="Soru 3", doc="d.pdf", evidence=["ev3"], category="single_fact")
    q4 = GoldenQuestion(id="Q4", question="Soru 4", doc="d.pdf", evidence=["ev4"], category="single_fact")

    c_ev1 = _make_chunk("c_ev1", "metin ev1")
    c_ev2 = _make_chunk("c_ev2", "metin ev2")
    c_ev3 = _make_chunk("c_ev3", "metin ev3")
    c_other = _make_chunk("c_other", "alakasiz metin")

    # Q1: Baseline rank 2 -> Rerank rank 1 (İyileşen)
    # Q2: Baseline rank 1 -> Rerank rank 2 (Bozulan)
    # Q3: Baseline rank 1 -> Rerank rank 1 (Değişmeyen)
    # Q4: Baseline rank None -> Rerank rank 1 (İyileşen)
    baseline_map = {
        "Q1": [c_other, c_ev1],
        "Q2": [c_ev2, c_other],
        "Q3": [c_ev3],
        "Q4": [c_other],
    }
    rerank_map = {
        "Q1": [c_ev1, c_other],
        "Q2": [c_other, c_ev2],
        "Q3": [c_ev3],
        "Q4": [c_ev4 := _make_chunk("c_ev4", "metin ev4")],
    }

    flips = classify_flips([q1, q2, q3, q4], baseline_map, rerank_map)

    improved_ids = [item["id"] for item in flips["improved"]]
    regressed_ids = [item["id"] for item in flips["regressed"]]

    assert "Q1" in improved_ids
    assert "Q4" in improved_ids
    assert "Q2" in regressed_ids
    assert flips["unchanged_count"] == 1


def test_compute_percentiles():
    latencies = [10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0, 80.0, 90.0, 100.0]
    p50, p95 = compute_percentiles(latencies)
    assert p50 == 60.0
    assert p95 == 100.0

    assert compute_percentiles([]) == (0.0, 0.0)


def test_run_comparison_e2e(tmp_path: Path):
    chunks = [
        _make_chunk("c1", "İade politikası 14 gündür."),
        _make_chunk("c2", "Kargo 1000 TL üzeri bedavadır."),
        _make_chunk("c3", "Garanti süresi 2 yıldır."),
    ]
    questions = [
        GoldenQuestion(
            id="Q1",
            question="İade süresi kaç gün?",
            doc="doc1.pdf",
            evidence=["14 gündür"],
            category="single_fact",
        )
    ]

    embedder = FakeEmbedder(dimensions=16)
    reranker = FakeReranker()
    client = QdrantClient(":memory:")

    report_data = run_comparison(
        embedder=embedder,
        reranker=reranker,
        chunks=chunks,
        questions=questions,
        client=client,
        modes=["hybrid"],
        candidate_counts=[5],  # 5 > 3 (toplam chunk 3) -> Doygunluk uyarısı tetiklenecek
        reports_dir=tmp_path,
    )

    # Rapor kontrolleri
    assert report_data["total_chunks"] == 3
    assert report_data["total_questions"] == 1

    cand_eval = report_data["results"]["hybrid"]["candidates_eval"]["5"]
    assert cand_eval["is_saturated"] is True  # total_chunks (3) <= candidates (5)

    # Dosyaların diske yazıldığını doğrula
    json_files = list(tmp_path.glob("*.json"))
    md_files = list(tmp_path.glob("*.md"))
    assert len(json_files) == 1
    assert len(md_files) == 1

    md_content = md_files[0].read_text(encoding="utf-8")
    assert "SMOKE TEST UYARISI" in md_content
    assert "DOYGUNLUK UYARISI" in md_content
    assert "DÜŞÜK ÖRNEKLEM BOYUTU" in md_content
    assert "Kategori Kırılımı" in md_content

    # Mükerrer arama önlendiği için reranker soru başına yalnızca 1 kez çağrılmış olmalı
    assert len(reranker.calls) == 1


def test_cached_retriever_partitions_by_query_and_k():
    class CountingRetriever(Retriever):
        def __init__(self):
            self.call_log = []

        def index(self, chunks):
            pass

        def search(self, query: str, k: int = 5):
            self.call_log.append((query, k))
            return [_make_chunk(f"c_{i}", f"doc {i}") for i in range(k)]

        def search_by_budget(self, query, budget, tokenizer):
            return []

    inner = CountingRetriever()
    cached = CachedRetriever(inner)

    # 1. İlk k=5 çağrısı inner'ı çağırır
    res1 = cached.search("soru1", k=5)
    assert len(res1) == 5
    assert len(inner.call_log) == 1
    assert inner.call_log[0] == ("soru1", 5)

    # 2. İkinci k=5 çağrısı önbellekten gelir, inner tekrar çağrılmaz
    res2 = cached.search("soru1", k=5)
    assert len(res2) == 5
    assert len(inner.call_log) == 1

    # 3. Aynı soru için k=20 çağrısı yapılırsa anahtar farklıdır ((soru1, 20)), inner çağrılır
    res3 = cached.search("soru1", k=20)
    assert len(res3) == 20
    assert len(inner.call_log) == 2
    assert inner.call_log[1] == ("soru1", 20)

    # 4. Farklı bir soru sorulursa ((soru2, 5)), inner çağrılır
    res4 = cached.search("soru2", k=5)
    assert len(res4) == 5
    assert len(inner.call_log) == 3
    assert inner.call_log[2] == ("soru2", 5)


