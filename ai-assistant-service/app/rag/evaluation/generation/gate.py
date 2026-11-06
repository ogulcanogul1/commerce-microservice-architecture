"""Dense cosine score distribution and abstain gate threshold analyzer.

Bu modül, LLM çağırmadan yalnızca en iyi dense kosinüs benzerlik skorlarını (top_dense_score)
ölçer. Cevaplanabilir (answerable=True) ve cevaplanamaz (answerable=False) soru gruplarının
skor dağılımlarını karşılaştırarak en az bilgi kaybıyla (en fazla 1 soru kaybı) en yüksek
halüsinasyon engelleme sağlayan RAG_MIN_DENSE_SCORE eşiğini önerir.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys
from typing import Any
import uuid

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

import numpy as np
from qdrant_client import QdrantClient

from app.core.config import settings
from app.rag.chunking import DefaultChunker
from app.rag.chunking.models import Chunk, ChunkingConfig
from app.rag.chunking.tokenizer import TiktokenTokenizer
from app.rag.embedding.base import Embedder
from app.rag.embedding.factory import get_default_embedder
from app.rag.embedding.fake import FakeEmbedder
from app.rag.evaluation.generation.dataset import (
    DEFAULT_ANSWER_SET_PATH,
    DEFAULT_GOLDEN_SET_PATH,
    AnswerCase,
    load_answer_set,
)
from app.rag.ingestion.pdf.loader import PDFLoader
from app.rag.vectorstore.models import QdrantConfig
from app.rag.vectorstore.search import search_dense
from app.rag.vectorstore.store import QdrantStore


def load_eval_chunks(docs_dir: Path) -> list[Chunk]:
    """Load evaluation PDF documents and split them using DefaultChunker."""
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
    """Create a temporary collection, index chunks with embeddings, and return store and collection name."""
    col_name = f"geneval_gate_{uuid.uuid4().hex[:8]}"
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
    store.upsert_chunks(chunks, dense_vecs, doc_hash="gate_eval_hash")
    return store, col_name


def measure_dense_scores(
    store: QdrantStore,
    embedder: Embedder,
    cases: list[AnswerCase],
) -> list[dict[str, Any]]:
    """Measure top dense cosine similarity score for each evaluation case."""
    results: list[dict[str, Any]] = []

    for case in cases:
        query_vec = embedder.embed_query(case.question)
        hits = search_dense(
            client=store.client,
            collection_name=store.collection_name,
            query_vec=query_vec,
            k=1,
        )
        top_score = hits[0].score if hits else 0.0

        results.append(
            {
                "id": case.id,
                "question": case.question,
                "answerable": case.answerable,
                "category": case.category,
                "top_dense_score": top_score,
            }
        )
    return results


def compute_distribution_stats(scores: list[float]) -> dict[str, float]:
    """Compute summary distribution statistics (min, p25, median, max)."""
    if not scores:
        return {"min": 0.0, "p25": 0.0, "median": 0.0, "max": 0.0}

    arr = np.array(scores)
    return {
        "min": float(np.min(arr)),
        "p25": float(np.percentile(arr, 25)),
        "median": float(np.median(arr)),
        "max": float(np.max(arr)),
    }


def analyze_thresholds(
    ans_scores: list[float],
    unans_scores: list[float],
) -> tuple[list[dict[str, Any]], float | None, str]:
    """Analyze trade-offs for candidate thresholds and recommend an optimal threshold.

    Kural:
    - Cevaplanabilir sorulardan en fazla 1 soru kaybettiren (lost_answerable <= 1) en yüksek eşik seçilir.
    - Eğer cevaplanabilir ve cevaplanamaz dağılımları aşırı örtüşüyorsa veya unanswerable
      soruları filtrelemede fayda sağlamıyorsa 'None' önerilir.
    """
    candidate_steps = [round(t, 2) for t in np.arange(0.30, 0.95, 0.05)]
    table: list[dict[str, Any]] = []

    best_thresh: float | None = None
    max_filtered_unans = -1

    for t in candidate_steps:
        lost_ans = sum(1 for s in ans_scores if s < t)
        filtered_unans = sum(1 for s in unans_scores if s < t)

        row = {
            "threshold": t,
            "lost_answerable": lost_ans,
            "lost_answerable_pct": (lost_ans / len(ans_scores)) * 100 if ans_scores else 0.0,
            "filtered_unanswerable": filtered_unans,
            "filtered_unanswerable_pct": (filtered_unans / len(unans_scores)) * 100 if unans_scores else 0.0,
        }
        table.append(row)

        # En fazla 1 cevaplanabilir kayıp kuralı
        if lost_ans <= 1 and filtered_unans > 0:
            if filtered_unans >= max_filtered_unans:
                best_thresh = t
                max_filtered_unans = filtered_unans

    # Öneri gerekçesi belirleme
    if best_thresh is not None and max_filtered_unans > 0:
        rationale = (
            f"Onerilen esik: {best_thresh:.2f} (En fazla 1 cevaplanabilir soru feda edilerek "
            f"{max_filtered_unans}/{len(unans_scores)} cevaplanamaz soru kapida elenir)."
        )
    else:
        rationale = (
            "Dagitimlar belirgin bicimde ortusuyor veya guvenli bir ayrim saglanamiyor. "
            "RAG_MIN_DENSE_SCORE = None olarak kalmali, abstain yukunu model ('BULUNAMADI') tasimalidir."
        )

    return table, best_thresh, rationale


def print_gate_report(
    ans_scores: list[float],
    unans_scores: list[float],
    table: list[dict[str, Any]],
    recommended_thresh: float | None,
    rationale: str,
) -> None:
    """Print formatted gate evaluation report to console."""
    ans_stats = compute_distribution_stats(ans_scores)
    unans_stats = compute_distribution_stats(unans_scores)

    print("\n" + "=" * 70)
    print(" RAG ABSTAIN GATESI - DENSE KOSINUS SKOR DAGILIMI")
    print("=" * 70)

    print("\n[1] Skor Ozet Istatistikleri:")
    print(f"  Cevaplanabilir (n={len(ans_scores)}):")
    print(f"    Min:    {ans_stats['min']:.4f}")
    print(f"    p25:    {ans_stats['p25']:.4f}")
    print(f"    Medyan: {ans_stats['median']:.4f}")
    print(f"    Max:    {ans_stats['max']:.4f}")

    print(f"\n  Cevaplanamaz (n={len(unans_scores)}):")
    print(f"    Min:    {unans_stats['min']:.4f}")
    print(f"    p25:    {unans_stats['p25']:.4f}")
    print(f"    Medyan: {unans_stats['median']:.4f}")
    print(f"    Max:    {unans_stats['max']:.4f}")

    print("\n[2] Aday Esik Degerleri Tablosu:")
    print(f"{'Esik':<8} | {'Kaybedilen Cevap':<18} | {'Elenen Cevaplanamaz':<20}")
    print("-" * 52)
    for r in table:
        t_str = f"{r['threshold']:.2f}"
        lost_str = f"{r['lost_answerable']} ({r['lost_answerable_pct']:.1f}%)"
        filt_str = f"{r['filtered_unanswerable']} ({r['filtered_unanswerable_pct']:.1f}%)"
        print(f"{t_str:<8} | {lost_str:<18} | {filt_str:<20}")

    print("\n[3] Eşik Karar Onerisi:")
    print(f"  -> {rationale}")
    print("=" * 70 + "\n")


def main() -> None:
    """CLI runner to measure dense score distributions and recommend abstain threshold."""
    parser = argparse.ArgumentParser(description="Dense Cosine Abstain Gate Eşik Ölçücü")
    parser.add_argument(
        "--docs-dir",
        type=Path,
        default=Path("eval/chunking/docs"),
        help="PDF dokümanlarının dizini",
    )
    parser.add_argument(
        "--answer-set-path",
        type=Path,
        default=DEFAULT_ANSWER_SET_PATH,
        help="Answer set dosya yolu",
    )
    parser.add_argument(
        "--golden-path",
        type=Path,
        default=DEFAULT_GOLDEN_SET_PATH,
        help="Golden set dosya yolu",
    )
    parser.add_argument(
        "--embedder",
        choices=["fake", "default"],
        default="default",
        help="Kullanılacak embedder sağlayıcısı",
    )
    parser.add_argument(
        "--client-mode",
        choices=["memory", "server"],
        default="memory",
        help="Qdrant modu: memory veya server",
    )

    args = parser.parse_args()

    # 1. Embedder hazırla
    if args.embedder == "fake":
        embedder: Embedder = FakeEmbedder(dimensions=64)
    else:
        try:
            embedder = get_default_embedder()
        except Exception as exc:
            print(f"[UYARI] Gerçek embedder başlatılamadı ({exc}), FakeEmbedder'a geçiliyor.")
            embedder = FakeEmbedder(dimensions=64)

    # 2. Qdrant İstemcisi
    if args.client_mode == "server":
        client = QdrantClient(url=settings.QDRANT_URL, api_key=settings.QDRANT_API_KEY or None)
    else:
        client = QdrantClient(":memory:")

    # 3. Dokümanları yükle ve geçici koleksiyon oluştur
    print("[*] PDF dokümanları yüklenip chunk'lara ayrılıyor...")
    chunks = load_eval_chunks(args.docs_dir)
    print(f"[*] Toplam {len(chunks)} chunk hazırlandı.")

    print("[*] Geçici koleksiyon kuruluyor ve chunk'lar indeksleniyor...")
    store, col_name = setup_temporary_store(client=client, embedder=embedder, chunks=chunks)

    try:
        # 4. Soruları yükle
        cases = load_answer_set(path=args.answer_set_path, golden_path=args.golden_path)
        print(f"[*] {len(cases)} soru için dense cosine benzerlik skorları hesaplanıyor...")

        scored_items = measure_dense_scores(store=store, embedder=embedder, cases=cases)

        ans_scores = [item["top_dense_score"] for item in scored_items if item["answerable"]]
        unans_scores = [item["top_dense_score"] for item in scored_items if not item["answerable"]]

        table, best_thresh, rationale = analyze_thresholds(ans_scores, unans_scores)
        print_gate_report(ans_scores, unans_scores, table, best_thresh, rationale)

    finally:
        # 5. Geçici koleksiyonu mutlaka sil
        try:
            client.delete_collection(col_name)
            print(f"[*] Gecici koleksiyon temizlendi: {col_name}")
        except Exception:
            pass


if __name__ == "__main__":
    main()
