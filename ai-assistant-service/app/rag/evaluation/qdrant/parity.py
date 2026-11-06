"""Qdrant Parite Değerlendirmesi (Parity Evaluation).

Bellek içi (In-Memory) Dense ve Hybrid retriever'lar ile Qdrant üzerindeki
QdrantRetriever(dense) ve QdrantRetriever(hybrid) modellerini birebir aynı
Golden Set ve doküman parçaları üzerinde yarıştırır.

Kabul Kriterleri:
  1. Dense Arama Sıralama Farkı: 0 olmalıdır (birebir aynı sıralama).
  2. Hybrid Hit@3 Farkı: En fazla 1 soru (yaklaşık %2.4) olabilir.
  3. İzolasyon: Test geçici bir koleksiyonda çalışır ve test sonunda koleksiyon silinir.
"""

from __future__ import annotations

import argparse
import datetime
import json
from pathlib import Path
import subprocess
import sys
import uuid
from typing import Any

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from qdrant_client import QdrantClient

from app.core.config import get_settings
from app.rag.chunking import DefaultChunker
from app.rag.chunking.models import Chunk, ChunkingConfig
from app.rag.chunking.tokenizer import TiktokenTokenizer
from app.rag.embedding.base import Embedder
from app.rag.embedding.factory import get_default_embedder
from app.rag.embedding.fake import FakeEmbedder
from app.rag.evaluation.chunking.dataset import GoldenQuestion, load_golden_set
from app.rag.evaluation.chunking.retrieval import (
    BM25Retriever,
    RetrievalEvalSummary,
    evaluate_retrieval,
)
from app.rag.evaluation.embedding.retrieval import DenseRetriever, HybridRetriever
from app.rag.ingestion.pdf.loader import PDFLoader
from app.rag.vectorstore.models import QdrantConfig
from app.rag.vectorstore.retriever import QdrantRetriever
from app.rag.vectorstore.store import QdrantStore


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


def evaluate_ranking_differences(
    retriever_a: Any,
    retriever_b: Any,
    questions: list[GoldenQuestion],
    k: int = 5,
) -> list[dict[str, Any]]:
    """İki retriever arasındaki top-k sıralama farklarını soru bazında analiz eder."""
    differences: list[dict[str, Any]] = []

    for q in questions:
        res_a = retriever_a.search(q.question, k=k)
        res_b = retriever_b.search(q.question, k=k)

        ids_a = [c.id for c in res_a]
        ids_b = [c.id for c in res_b]

        if ids_a != ids_b:
            # Skor eşitliği (tie) kontrolü: Eğer aynı elemanlar kümesi ise ve yer değiştirenler
            # eşit skora sahipse (floating point tie), bu gerçek bir sıralama hatası değildir.
            is_score_tie = False
            if set(ids_a) == set(ids_b) and hasattr(retriever_a, "matrix") and retriever_a.matrix is not None:
                q_vec = retriever_a.embedder.embed_query(q.question)
                scores = retriever_a.matrix @ q_vec
                id_to_score = {c.id: float(scores[i]) for i, c in enumerate(retriever_a.chunks)}
                diff_scores = [abs(id_to_score[a] - id_to_score[b]) for a, b in zip(ids_a, ids_b) if a != b]
                if diff_scores and max(diff_scores) < 1e-4:
                    is_score_tie = True

            if not is_score_tie:
                differences.append({
                    "question_id": q.id,
                    "question": q.question,
                    "retriever_a_ids": ids_a,
                    "retriever_b_ids": ids_b,
                    "same_elements_different_order": set(ids_a) == set(ids_b),
                })

    return differences


def run_parity_evaluation(
    embedder: Embedder,
    questions: list[GoldenQuestion],
    all_chunks: list[Chunk],
    client: QdrantClient,
    reports_dir: Path | None = None,
) -> dict[str, Any]:
    """Bellek içi vs Qdrant parite testini baştan sona çalıştırır ve rapor döner."""
    # 1. Aşama: Bellek İçi Retriever'ları Değerlendir
    print("[1/4] Bellek İçi DenseRetriever değerlendiriliyor...")
    in_mem_dense = DenseRetriever(embedder)
    summary_dense_mem, q_dense_mem = evaluate_retrieval(in_mem_dense, questions, all_chunks)

    print("[2/4] Bellek İçi HybridRetriever (RRF) değerlendiriliyor...")
    in_mem_bm25 = BM25Retriever()
    in_mem_hybrid = HybridRetriever(dense=in_mem_dense, bm25=in_mem_bm25, dense_weight=0.5)
    summary_hybrid_mem, q_hybrid_mem = evaluate_retrieval(in_mem_hybrid, questions, all_chunks)

    # 2. Aşama: Geçici Koleksiyonda Qdrant Retriever'ları Değerlendir
    temp_col = f"commerce_docs_eval_{uuid.uuid4().hex[:8]}"
    print(f"[3/4] Qdrant üzerinde geçici koleksiyon açılıyor: {temp_col}...")

    qdrant_config = QdrantConfig(collection_prefix="eval", upsert_batch_size=50)
    store = QdrantStore(
        client=client,
        config=qdrant_config,
        embedder=embedder,
        collection_name=temp_col,
    )
    store.ensure_collection(embedder=embedder, collection_name=temp_col)
    store.ensure_payload_indexes()

    # Chunk'ları Qdrant koleksiyonuna bir defa indeksle
    print(f"[*] {len(all_chunks)} chunk Qdrant'a yazılıyor...")
    dense_vecs = embedder.embed_documents([c.embedding_text for c in all_chunks])
    store.upsert_chunks(all_chunks, dense_vecs, doc_hash="parity_eval_hash")

    try:
        print("[4/4] Qdrant Dense ve Hybrid retriever'lar değerlendiriliyor...")
        qdrant_dense = QdrantRetriever(store=store, embedder=embedder, mode="dense")
        summary_dense_qdrant, q_dense_qdrant = evaluate_retrieval(qdrant_dense, questions, all_chunks)

        qdrant_hybrid = QdrantRetriever(store=store, embedder=embedder, mode="hybrid")
        summary_hybrid_qdrant, q_hybrid_qdrant = evaluate_retrieval(qdrant_hybrid, questions, all_chunks)

        # 3. Aşama: Sıralama Birebir Fark Analizi
        dense_ranking_diffs = evaluate_ranking_differences(in_mem_dense, qdrant_dense, questions, k=5)
        hybrid_ranking_diffs = evaluate_ranking_differences(in_mem_hybrid, qdrant_hybrid, questions, k=5)

    finally:
        # Geçici koleksiyonu mutlaka temizle (İzolasyon kuralı)
        try:
            client.delete_collection(temp_col)
            print(f"[+] Geçici koleksiyon temizlendi: {temp_col}")
        except Exception as e:
            print(f"[UYARI] Geçici koleksiyon silinemedi: {e}")

    # 4. Aşama: Kabul Kriterleri Doğrulaması
    total_q = len(questions)
    hybrid_hit3_diff_questions = abs(summary_hybrid_mem.hit_at_3 - summary_hybrid_qdrant.hit_at_3) * total_q
    dense_diff_count = len(dense_ranking_diffs)

    dense_passed = (dense_diff_count == 0)
    hybrid_passed = (hybrid_hit3_diff_questions <= 1.05)  # En fazla 1 soru farkı (tolerans payı ile)

    all_passed = dense_passed and hybrid_passed

    report_data = {
        "timestamp": datetime.datetime.now().isoformat(),
        "git_commit": get_git_commit_hash(),
        "embedder_id": embedder.model_id,
        "total_chunks": len(all_chunks),
        "total_questions": total_q,
        "is_corpus_saturated": len(all_chunks) <= 15 and summary_dense_mem.hit_at_5 >= 0.95,
        "criteria": {
            "dense_ranking_diffs": dense_diff_count,
            "dense_passed": dense_passed,
            "hybrid_hit3_diff_questions": round(hybrid_hit3_diff_questions, 2),
            "hybrid_passed": hybrid_passed,
            "all_passed": all_passed,
        },
        "metrics": {
            "in_memory_dense": summary_dense_mem.model_dump(),
            "qdrant_dense": summary_dense_qdrant.model_dump(),
            "in_memory_hybrid": summary_hybrid_mem.model_dump(),
            "qdrant_hybrid": summary_hybrid_qdrant.model_dump(),
        },
        "differences": {
            "dense_differences": dense_ranking_diffs,
            "hybrid_differences": hybrid_ranking_diffs,
        },
    }

    # 5. Aşama: Rapor Dosyalarını Oluştur
    if reports_dir:
        reports_dir.mkdir(parents=True, exist_ok=True)
        today_str = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        slug_hash = uuid.uuid4().hex[:6]
        base_name = f"parity-{today_str}-{slug_hash}"

        # JSON Raporu
        json_path = reports_dir / f"{base_name}.json"
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(report_data, f, indent=2, ensure_ascii=False)

        # Markdown Raporu
        md_path = reports_dir / f"{base_name}.md"
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(_generate_markdown_report(report_data))

        report_data["report_files"] = {
            "json": str(json_path),
            "markdown": str(md_path),
        }
        print(f"[+] Rapor kaydedildi: {md_path}")

    return report_data


def _generate_markdown_report(data: dict[str, Any]) -> str:
    """Parite testi için detaylı Markdown raporu üretir."""
    crit = data["criteria"]
    m = data["metrics"]
    imd = m["in_memory_dense"]
    qd = m["qdrant_dense"]
    imh = m["in_memory_hybrid"]
    qh = m["qdrant_hybrid"]

    status_badge = "✅ BAŞARILI (PARITY ACHIEVED)" if crit["all_passed"] else "❌ BAŞARISIZ (PARITY FAILED)"

    lines = [
        f"# Qdrant vs Bellek İçi Parite Değerlendirme Raporu",
        f"",
        f"- **Tarih:** {data['timestamp']}",
        f"- **Git Commit:** `{data['git_commit']}`",
        f"- **Embedder Modeli:** `{data['embedder_id']}`",
        f"- **Toplam Doküman Parçası (Chunk):** {data['total_chunks']}",
        f"- **Toplam Golden Soru:** {data['total_questions']}",
        f"- **Genel Durum:** **{status_badge}**",
        f"",
    ]

    if data.get("is_corpus_saturated"):
        lines.extend([
            "> [!WARNING] **Korpus Yapısal Olarak Doygun (Structural Saturation)**",
            f"> Test korpusu yalnızca {data['total_chunks']} chunk içermektedir. "
            f"Hit@3 ve Hit@5 oranlarının %95-%100 çıkması istatistiksel üstünlük değil, "
            f"küçük veri setinde top-k seçiminin korpusun büyük kısmını kapsamasından kaynaklanan yapısal bir doygunluktur. "
            f"Büyük doküman korpusu yüklendiğinde metrikler yeniden doğrulanmalıdır.",
            "",
        ])

    lines.extend([
        "## 1. Karşılaştırma ve Kabul Kriterleri Tablosu",
        "",
        "| Arama Yöntemi | Metrik | Bellek İçi (RAM) | Qdrant (Veritabanı) | Fark | Kabul Kriteri | Durum |",
        "|---|---|---|---|---|---|---|",
        f"| **Dense (Anlamsal)** | Hit@1 | %{round(imd['hit_at_1']*100, 1)} | %{round(qd['hit_at_1']*100, 1)} | {round((qd['hit_at_1']-imd['hit_at_1'])*100, 1)}% | Sıralama Farkı = 0 | {'✅' if crit['dense_passed'] else '❌'} |",
        f"| **Dense (Anlamsal)** | Hit@3 | %{round(imd['hit_at_3']*100, 1)} | %{round(qd['hit_at_3']*100, 1)} | {round((qd['hit_at_3']-imd['hit_at_3'])*100, 1)}% | Sıralama Farkı = 0 | {'✅' if crit['dense_passed'] else '❌'} |",
        f"| **Dense (Anlamsal)** | MRR   | {round(imd['mrr'], 3)} | {round(qd['mrr'], 3)} | {round(qd['mrr']-imd['mrr'], 3)} | Birebir Eşitlik | {'✅' if crit['dense_passed'] else '❌'} |",
        f"| **Hybrid (RRF)**     | Hit@1 | %{round(imh['hit_at_1']*100, 1)} | %{round(qh['hit_at_1']*100, 1)} | {round((qh['hit_at_1']-imh['hit_at_1'])*100, 1)}% | Referans | - |",
        f"| **Hybrid (RRF)**     | Hit@3 | %{round(imh['hit_at_3']*100, 1)} | %{round(qh['hit_at_3']*100, 1)} | {round(crit['hybrid_hit3_diff_questions'], 1)} soru | ≤ 1 Soru (≈ %2.4) | {'✅' if crit['hybrid_passed'] else '❌'} |",
        f"| **Hybrid (RRF)**     | MRR   | {round(imh['mrr'], 3)} | {round(qh['mrr'], 3)} | {round(qh['mrr']-imh['mrr'], 3)} | Referans | - |",
        "",
        "## 2. Kriter Detayları",
        f"- **Dense Sıralama Farkı:** `{crit['dense_ranking_diffs']}` soru (Hedef: 0).",
        f"- **Hybrid Hit@3 Farkı:** `{crit['hybrid_hit3_diff_questions']}` soru farkı (Hedef: ≤ 1 soru).",
        "",
    ])

    hybrid_diffs = data["differences"]["hybrid_differences"]
    if hybrid_diffs:
        lines.extend([
            f"## 3. Hibrit Aramada Sıralaması Farklılaşan Sorular ({len(hybrid_diffs)} adet)",
            "> Not: Qdrant sunucu taraflı BM25 (sparse+IDF) formülü ile Python bellek içi BM25Okapi formülü "
            "arasındaki matematiksel farklar nedeniyle sıralamalarda küçük yer değişimleri doğaldır.",
            "",
            "| Soru ID | Soru Metni | Bellek İçi Top-3 ID | Qdrant Top-3 ID |",
            "|---|---|---|---|",
        ])
        for d in hybrid_diffs[:10]:  # İlk 10 tanesini listele
            lines.append(
                f"| `{d['question_id']}` | {d['question']} | `{', '.join(d['retriever_a_ids'][:3])}` | `{', '.join(d['retriever_b_ids'][:3])}` |"
            )
        lines.append("")

    return "\n".join(lines)


def main() -> None:
    """CLI giriş noktası."""
    parser = argparse.ArgumentParser(description="Qdrant Parite Değerlendirme Aracı")
    parser.add_argument(
        "--embedder",
        default="fake",
        help="Kullanılacak embedder: 'fake' veya 'default' (varsayılan: fake)",
    )
    parser.add_argument(
        "--golden",
        type=Path,
        default=Path("eval/chunking/golden_set.json"),
        help="Golden set JSON dosya yolu",
    )
    parser.add_argument(
        "--docs-dir",
        type=Path,
        default=Path("eval/chunking/docs"),
        help="PDF dokümanlarının dizini",
    )
    parser.add_argument(
        "--reports-dir",
        type=Path,
        default=Path("eval/qdrant/reports"),
        help="Raporların kaydedileceği dizin",
    )
    parser.add_argument(
        "--client-mode",
        choices=["memory", "server"],
        default="memory",
        help="Qdrant çalışma modu: ':memory:' veya Docker 'server' (varsayılan: memory)",
    )
    args = parser.parse_args()

    # 1. Dokümanları ve Soruları Yükle
    if not args.docs_dir.exists():
        print(f"[HATA] Doküman dizini bulunamadı: {args.docs_dir}")
        sys.exit(1)

    pdf_files = sorted(args.docs_dir.glob("*.pdf"))
    if not pdf_files:
        print(f"[HATA] {args.docs_dir} içinde PDF dokümanı bulunamadı!")
        sys.exit(1)

    print(f"[*] {len(pdf_files)} PDF dokümanı okunuyor...")
    loader = PDFLoader()
    documents = [loader.load(p) for p in pdf_files]

    questions = load_golden_set(args.golden)
    tokenizer = TiktokenTokenizer()
    chunker = DefaultChunker(tokenizer=tokenizer, config=ChunkingConfig())

    all_chunks: list[Chunk] = []
    for doc in documents:
        all_chunks.extend(chunker.chunk(doc))

    print(f"[*] {len(all_chunks)} chunk oluşturuldu.")
    print(f"[*] {len(questions)} Golden soru yüklendi.")

    # 2. Embedder'ı Belirle
    if args.embedder == "fake":
        embedder: Embedder = FakeEmbedder(dimensions=64, model_id="fake/deterministic-bow")
    else:
        embedder = get_default_embedder()

    # 3. Qdrant İstemcisini Oluştur
    if args.client_mode == "server":
        settings = get_settings()
        client = QdrantClient(url=settings.QDRANT_URL, api_key=settings.QDRANT_API_KEY or None)
        print(f"[*] Gerçek Qdrant sunucusuna bağlanıldı: {settings.QDRANT_URL}")
    else:
        client = QdrantClient(":memory:")
        print("[*] Yerel hafıza içi Qdrant istemcisi (:memory:) başlatıldı.")

    # 4. Parite Testini Koş
    report = run_parity_evaluation(
        embedder=embedder,
        questions=questions,
        all_chunks=all_chunks,
        client=client,
        reports_dir=args.reports_dir,
    )

    crit = report["criteria"]
    print("\n================= PARİTE TEST SONUCU =================")
    print(f"Dense Sıralama Farkı    : {crit['dense_ranking_diffs']} soru -> {'GEÇTİ (PASSED)' if crit['dense_passed'] else 'KALDI'}")
    print(f"Hybrid Hit@3 Farkı      : {crit['hybrid_hit3_diff_questions']} soru -> {'GEÇTİ (PASSED)' if crit['hybrid_passed'] else 'KALDI'}")
    print(f"Genel Parite Durumu     : {'✅ BAŞARILI (TÜM KRİTERLER SAĞLANDI)' if crit['all_passed'] else '❌ BAŞARISIZ'}")
    print("======================================================\n")

    if not crit["all_passed"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
