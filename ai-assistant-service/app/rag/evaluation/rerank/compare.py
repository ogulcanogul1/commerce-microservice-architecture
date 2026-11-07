"""Retrieval-level A/B comparison runner evaluating baseline vs. reranker performance."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
import datetime
import json
import logging
from pathlib import Path
import subprocess
import sys
import time
from typing import Any
import uuid

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from qdrant_client import QdrantClient

from app.core.config import settings
from app.rag.chunking import DefaultChunker
from app.rag.chunking.models import Chunk, ChunkingConfig
from app.rag.chunking.tokenizer import TiktokenTokenizer
from app.rag.embedding.base import Embedder
from app.rag.embedding.factory import get_default_embedder
from app.rag.embedding.fake import FakeEmbedder
from app.rag.evaluation.chunking.dataset import GoldenQuestion, load_golden_set
from app.rag.evaluation.chunking.retrieval import (
    RetrievalEvalSummary,
    Retriever,
    chunk_contains_evidence,
    evaluate_retrieval,
)
from app.rag.ingestion.pdf.loader import PDFLoader
from app.rag.rerank.base import Reranker
from app.rag.rerank.factory import get_reranker
from app.rag.rerank.retriever import RerankingRetriever
from app.rag.vectorstore.models import QdrantConfig
from app.rag.vectorstore.retriever import QdrantRetriever
from app.rag.vectorstore.store import QdrantStore

logger = logging.getLogger(__name__)

DEFAULT_DOCS_DIR = Path("eval/chunking/docs")
DEFAULT_GOLDEN_PATH = Path("eval/chunking/golden_set.json")
DEFAULT_REPORTS_DIR = Path("eval/rerank/reports")


def get_git_commit_hash() -> str:
    """Mevcut git commit hash'ini ve çalışma dizininin temizlik durumunu döner."""
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], stderr=subprocess.DEVNULL
        )
        h = out.decode("utf-8").strip()
        status = subprocess.check_output(
            ["git", "status", "--porcelain"], stderr=subprocess.DEVNULL
        )
        if status.strip():
            return f"{h} (dirty)"
        return h
    except Exception:
        return "unknown"


def first_correct_rank(retrieved: Sequence[Chunk], evidence: list[str]) -> int | None:
    """Get 1-based index of the first chunk containing the complete evidence, or None."""
    for rank, chunk in enumerate(retrieved, start=1):
        if chunk_contains_evidence(chunk, evidence):
            return rank
    return None


def classify_flips(
    questions: list[GoldenQuestion],
    baseline_chunks_by_q: dict[str, list[Chunk]],
    rerank_chunks_by_q: dict[str, list[Chunk]],
) -> dict[str, Any]:
    """Classify questions into improved, regressed, and unchanged based on first correct rank."""
    improved: list[dict[str, Any]] = []
    regressed: list[dict[str, Any]] = []
    unchanged_count = 0

    for q in questions:
        b_chunks = baseline_chunks_by_q.get(q.id, [])
        r_chunks = rerank_chunks_by_q.get(q.id, [])

        b_rank = first_correct_rank(b_chunks, q.evidence)
        r_rank = first_correct_rank(r_chunks, q.evidence)

        # Sıra düştü (örn: 3 -> 1) veya baseline bulamadı ama reranker buldu
        is_improved = False
        is_regressed = False

        if b_rank is None and r_rank is not None:
            is_improved = True
        elif b_rank is not None and r_rank is not None:
            if r_rank < b_rank:
                is_improved = True
            elif r_rank > b_rank:
                is_regressed = True
        elif b_rank is not None and r_rank is None:
            is_regressed = True

        if is_improved:
            improved.append({
                "id": q.id,
                "question": q.question,
                "baseline_rank": b_rank,
                "rerank_rank": r_rank,
            })
        elif is_regressed:
            regressed.append({
                "id": q.id,
                "question": q.question,
                "baseline_rank": b_rank,
                "rerank_rank": r_rank,
            })
        else:
            unchanged_count += 1

    return {
        "improved": improved,
        "regressed": regressed,
        "unchanged_count": unchanged_count,
    }


def compute_percentiles(latencies: list[float]) -> tuple[float, float]:
    """Hesaplanan gecikmelerin p50 ve p95 değerlerini döner."""
    if not latencies:
        return 0.0, 0.0
    sorted_l = sorted(latencies)
    p50_idx = min(int(len(sorted_l) * 0.50), len(sorted_l) - 1)
    p95_idx = min(int(len(sorted_l) * 0.95), len(sorted_l) - 1)
    return round(sorted_l[p50_idx], 2), round(sorted_l[p95_idx], 2)


class CachedRetriever(Retriever):
    """Retriever arama çağrılarını hafızada tutarak flip analizi için mükerrer aramayı ve çift gecikme ölçümünü önler."""

    def __init__(self, inner: Retriever) -> None:
        self.inner = inner
        self.cache: dict[tuple[str, int], list[Chunk]] = {}

    def index(self, chunks: Sequence[Chunk]) -> None:
        self.inner.index(chunks)

    def search(self, query: str, k: int = 5) -> list[Chunk]:
        key = (query, k)
        if key not in self.cache:
            self.cache[key] = self.inner.search(query, k=k)
        return self.cache[key]

    def search_by_budget(
        self, query: str, budget: int, tokenizer: Any
    ) -> list[Chunk]:
        return self.inner.search_by_budget(query, budget, tokenizer)


def load_eval_chunks(docs_dir: Path) -> list[Chunk]:
    """PDF dokümanlarını yükleyip DefaultChunker ile parçalar."""
    pdf_files = sorted(docs_dir.glob("*.pdf"))
    if not pdf_files:
        raise FileNotFoundError(f"{docs_dir} içinde PDF dokümanı bulunamadı.")

    loader = PDFLoader()
    tokenizer = TiktokenTokenizer()
    chunker = DefaultChunker(tokenizer=tokenizer, config=ChunkingConfig())

    chunks: list[Chunk] = []
    for pdf in pdf_files:
        doc = loader.load(pdf)
        chunks.extend(chunker.chunk(doc))
    return chunks


def setup_temporary_store(
    client: QdrantClient,
    embedder: Embedder,
    chunks: list[Chunk],
) -> tuple[QdrantStore, str]:
    """Geçici bir Qdrant koleksiyonu oluşturup chunk'ları indeksler."""
    col_name = f"rerankeval_{uuid.uuid4().hex[:8]}"
    config = QdrantConfig(
        url="http://localhost:6333",
        collection_prefix="eval",
        upsert_batch_size=50,
    )
    store = QdrantStore(
        client=client,
        config=config,
        embedder=embedder,
        collection_name=col_name,
    )
    store.ensure_collection(embedder=embedder, collection_name=col_name)
    store.ensure_payload_indexes()

    dense_vecs = embedder.embed_documents([c.embedding_text for c in chunks])
    store.upsert_chunks(chunks, dense_vecs, doc_hash="rerankeval_hash")
    return store, col_name


def run_comparison(
    embedder: Embedder,
    reranker: Reranker,
    chunks: list[Chunk],
    questions: list[GoldenQuestion],
    client: QdrantClient,
    modes: list[str],
    candidate_counts: list[int],
    reports_dir: Path,
) -> dict[str, Any]:
    """Tüm modlar ve aday sayıları için karşılaştırmayı yürütür, rapor üretir."""
    store, temp_col = setup_temporary_store(client, embedder, chunks)
    total_chunks = len(chunks)
    total_questions = len(questions)

    results_by_mode: dict[str, Any] = {}

    try:
        for mode in modes:
            print(f"\n[*] Değerlendirme modu: {mode.upper()}")
            baseline_retriever = QdrantRetriever(store=store, embedder=embedder, mode=mode)  # type: ignore[arg-type]
            cached_baseline = CachedRetriever(baseline_retriever)
            
            # Baseline evaluate_retrieval
            base_summary, _ = evaluate_retrieval(cached_baseline, questions, chunks)
            
            # Baseline ranked chunks by question (k=5) - cache'ten döner, ekstra arama yapmaz
            base_chunks_by_q = {q.id: cached_baseline.search(q.question, k=5) for q in questions}

            mode_results: dict[str, Any] = {
                "baseline_summary": base_summary.model_dump(),
                "candidates_eval": {},
            }

            for candidates in candidate_counts:
                print(f"  -> Reranker aday sayısı: {candidates}")
                reranking_retriever = RerankingRetriever(
                    inner=baseline_retriever,
                    reranker=reranker,
                    candidates=candidates,
                )
                cached_rerank = CachedRetriever(reranking_retriever)

                rerank_summary, _ = evaluate_retrieval(cached_rerank, questions, chunks)
                rerank_chunks_by_q = {q.id: cached_rerank.search(q.question, k=5) for q in questions}

                flips = classify_flips(questions, base_chunks_by_q, rerank_chunks_by_q)
                p50, p95 = compute_percentiles(reranking_retriever.total_rerank_ms)

                # Doygunluk ve tavan uyarısı
                is_saturated = total_chunks <= candidates
                ceiling_hit = base_summary.hit_at_5 >= 0.95

                mode_results["candidates_eval"][str(candidates)] = {
                    "summary": rerank_summary.model_dump(),
                    "flips": flips,
                    "latency_p50_ms": p50,
                    "latency_p95_ms": p95,
                    "is_saturated": is_saturated,
                    "ceiling_hit": ceiling_hit,
                }

            results_by_mode[mode] = mode_results

    finally:
        try:
            client.delete_collection(temp_col)
            print(f"[+] Geçici koleksiyon temizlendi: {temp_col}")
        except Exception as exc:
            logger.warning("Geçici koleksiyon silinemedi: %s", exc)

    # Rapor nesnesini oluştur
    now_str = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    run_id = f"rerank-{now_str}-{uuid.uuid4().hex[:6]}"
    report_data = {
        "run_id": run_id,
        "timestamp": datetime.datetime.now().isoformat(),
        "git_commit": get_git_commit_hash(),
        "embedder_id": embedder.model_id,
        "reranker_id": reranker.model_id,
        "total_chunks": total_chunks,
        "total_questions": total_questions,
        "modes": modes,
        "candidate_counts": candidate_counts,
        "results": results_by_mode,
    }

    # Markdown ve JSON raporlarını yaz
    reports_dir.mkdir(parents=True, exist_ok=True)
    json_path = reports_dir / f"{run_id}.json"
    md_path = reports_dir / f"{run_id}.md"

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(report_data, f, ensure_ascii=False, indent=2)

    md_content = generate_markdown_report(report_data)
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md_content)

    print(f"\n[✓] Raporlar oluşturuldu:\n    JSON: {json_path}\n    MD:   {md_path}")
    return report_data


def generate_markdown_report(data: dict[str, Any]) -> str:
    """Rapor verisinden Markdown çıktısı üretir."""
    lines: list[str] = []
    lines.append(f"# Retrieval A/B Karşılaştırma Raporu: {data['run_id']}")
    lines.append("")
    lines.append(f"- **Tarih:** {data['timestamp']}")
    lines.append(f"- **Git Commit:** `{data['git_commit']}`")
    lines.append(f"- **Embedder:** `{data['embedder_id']}`")
    lines.append(f"- **Reranker:** `{data['reranker_id']}`")
    lines.append(f"- **Toplam Doküman Parçası (Chunk):** {data['total_chunks']}")
    lines.append(f"- **Toplam Soru:** {data['total_questions']}")
    lines.append("")

    if "fake" in data["reranker_id"].lower():
        lines.append("> [!NOTE]")
        lines.append("> **SMOKE TEST UYARISI:** Bu koşu FakeReranker ile gerçekleştirilmiştir; kalite göstergesi değildir.")
        lines.append("")

    if data.get("total_questions", 0) < 10:
        lines.append("> [!WARNING]")
        lines.append(
            f"> **DÜŞÜK ÖRNEKLEM BOYUTU (n={data.get('total_questions')} < 10):** "
            "Soru sayısı istatistiksel genelleme için yetersizdir. "
            "Bu sonuçları kesin kalite kararı olarak yorumlamayınız."
        )
        lines.append("")

    # Uyarılar
    total_chunks = data["total_chunks"]
    for mode, mode_data in data["results"].items():
        for cand_str, cand_data in mode_data["candidates_eval"].items():
            cand_int = int(cand_str)
            if cand_data.get("is_saturated"):
                lines.append(
                    f"> [!WARNING]\n"
                    f"> **DOYGUNLUK UYARISI ({mode.upper()} - Cand: {cand_int}):** "
                    f"Aday havuzu ({cand_int}) toplam corpus chunk sayısını ({total_chunks}) kapsıyor. "
                    f"Reranker aday kümesini değiştiremez, yalnızca sıralamayı değiştirebilir; bu sonuç karar için yetersizdir.\n"
                )
            if cand_data.get("ceiling_hit"):
                base_hit5 = mode_data["baseline_summary"]["hit_at_5"] * 100
                lines.append(
                    f"> [!IMPORTANT]\n"
                    f"> **TAVAN ETKİSİ ({mode.upper()}):** Baseline Hit@5 zaten tavan seviyesindedir (%{base_hit5:.1f}).\n"
                )

    # Özet Metrik Tablosu
    lines.append("## Özet Metrik Tablosu")
    lines.append("")
    lines.append("| Mod | Yapılandırma | Hit@1 | Hit@3 | Hit@5 | MRR | Rerank p50 (ms) | Rerank p95 (ms) |")
    lines.append("| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |")

    for mode, mode_data in data["results"].items():
        base = mode_data["baseline_summary"]
        lines.append(
            f"| {mode} | **Baseline** | {base['hit_at_1']:.3f} | {base['hit_at_3']:.3f} | "
            f"{base['hit_at_5']:.3f} | {base['mrr']:.3f} | - | - |"
        )
        for cand_str, cand_data in mode_data["candidates_eval"].items():
            s = cand_data["summary"]
            d_hit1 = s["hit_at_1"] - base["hit_at_1"]
            d_hit3 = s["hit_at_3"] - base["hit_at_3"]
            d_hit5 = s["hit_at_5"] - base["hit_at_5"]
            d_mrr = s["mrr"] - base["mrr"]

            sign1 = "+" if d_hit1 > 0 else ""
            sign3 = "+" if d_hit3 > 0 else ""
            sign5 = "+" if d_hit5 > 0 else ""
            sign_mrr = "+" if d_mrr > 0 else ""

            lines.append(
                f"| {mode} | Rerank (cand={cand_str}) | {s['hit_at_1']:.3f} ({sign1}{d_hit1:.3f}) | "
                f"{s['hit_at_3']:.3f} ({sign3}{d_hit3:.3f}) | {s['hit_at_5']:.3f} ({sign5}{d_hit5:.3f}) | "
                f"{s['mrr']:.3f} ({sign_mrr}{d_mrr:.3f}) | {cand_data['latency_p50_ms']} | {cand_data['latency_p95_ms']} |"
            )

    # Kategori Kırılımı ve Flip Analizi
    for mode, mode_data in data["results"].items():
        lines.append(f"\n## {mode.upper()} Arama Detayları ve Flip Analizi\n")

        for cand_str, cand_data in mode_data["candidates_eval"].items():
            flips = cand_data["flips"]
            lines.append(f"### Aday Sayısı: {cand_str}")
            lines.append(f"- **İyileşen Soru Sayısı:** {len(flips['improved'])}")
            lines.append(f"- **Bozulan Soru Sayısı:** {len(flips['regressed'])}")
            lines.append(f"- **Değişmeyen Soru Sayısı:** {flips['unchanged_count']}")
            lines.append("")

            # Kategori Kırılımı (Hit@3)
            base_cats = mode_data["baseline_summary"].get("category_hit3", {})
            cand_cats = cand_data["summary"].get("category_hit3", {})
            all_cats = sorted(set(base_cats.keys()).union(cand_cats.keys()))
            if all_cats:
                lines.append("#### 📊 Kategori Kırılımı (Hit@3)\n")
                lines.append("| Kategori | Baseline Hit@3 | Reranker Hit@3 | Fark (Δ) |")
                lines.append("| :--- | :--- | :--- | :--- |")
                for cat in all_cats:
                    b_val = base_cats.get(cat, 0.0)
                    r_val = cand_cats.get(cat, 0.0)
                    diff = r_val - b_val
                    sign = "+" if diff > 0 else ""
                    lines.append(f"| {cat} | %{b_val * 100:.1f} | %{r_val * 100:.1f} | {sign}%{diff * 100:.1f} |")
                lines.append("")

            if flips["improved"]:
                lines.append("#### 🟢 İyileşen Sorular")
                for item in flips["improved"]:
                    lines.append(
                        f"- `{item['id']}`: {item['question']} "
                        f"(`Rank: {item['baseline_rank']} -> {item['rerank_rank']}`)"
                    )
                lines.append("")

            if flips["regressed"]:
                lines.append("#### 🔴 Bozulan Sorular")
                for item in flips["regressed"]:
                    lines.append(
                        f"- `{item['id']}`: {item['question']} "
                        f"(`Rank: {item['baseline_rank']} -> {item['rerank_rank']}`)"
                    )
                lines.append("")

    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Retrieval A/B Karşılaştırma Çalıştırıcısı")
    parser.add_argument("--embedder", choices=["default", "fake"], default="fake")
    parser.add_argument("--reranker", choices=["fake", "cross_encoder", "cohere"], default="fake")
    parser.add_argument("--model", type=str, default="", help="Rerank model adı")
    parser.add_argument(
        "--candidates",
        type=int,
        nargs="+",
        default=[20],
        help="Aday sayıları (örn: --candidates 10 20 30)",
    )
    parser.add_argument(
        "--mode",
        type=str,
        nargs="+",
        choices=["dense", "hybrid"],
        default=["hybrid"],
        help="Arama modları",
    )
    parser.add_argument("--client-mode", choices=["memory", "server"], default="memory")
    parser.add_argument("--docs-dir", type=Path, default=DEFAULT_DOCS_DIR)
    parser.add_argument("--golden-path", type=Path, default=DEFAULT_GOLDEN_PATH)
    parser.add_argument("--reports-dir", type=Path, default=DEFAULT_REPORTS_DIR)

    args = parser.parse_args()

    # 1. Embedder yükle
    if args.embedder == "fake":
        embedder: Embedder = FakeEmbedder(dimensions=16)
    else:
        embedder = get_default_embedder()

    # 2. Reranker yükle
    reranker = get_reranker(args.reranker, model_name=args.model or None)

    # 3. Doküman ve Golden Set yükle
    print(f"[*] Dokümanlar yükleniyor: {args.docs_dir}")
    chunks = load_eval_chunks(args.docs_dir)
    print(f"[*] {len(chunks)} doküman parçası hazırlandı.")

    print(f"[*] Altın soru seti yükleniyor: {args.golden_path}")
    questions = load_golden_set(args.golden_path)
    print(f"[*] {len(questions)} test sorusu yüklendi.")

    # 4. Qdrant Client
    if args.client_mode == "memory":
        client = QdrantClient(":memory:")
    else:
        client = QdrantClient(url=settings.QDRANT_URL, api_key=settings.QDRANT_API_KEY or None)

    run_comparison(
        embedder=embedder,
        reranker=reranker,
        chunks=chunks,
        questions=questions,
        client=client,
        modes=args.mode,
        candidate_counts=args.candidates,
        reports_dir=args.reports_dir,
    )


if __name__ == "__main__":
    main()
