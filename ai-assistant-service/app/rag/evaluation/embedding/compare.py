"""Embedding model benchmark runner and report generator.

Compares candidate embedding models against BM25 baseline and each other across
accuracy (Hit@1, Hit@3, Hit@5, MRR) and operational metrics (latency, storage, cost).
"""

import argparse
import datetime
import json
from pathlib import Path
import subprocess
import sys
import time
from typing import Any

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from app.core.config import settings
from app.rag.chunking import DefaultChunker
from app.rag.chunking.models import Chunk, ChunkingConfig
from app.rag.chunking.tokenizer import TiktokenTokenizer
from app.rag.embedding.base import Embedder
from app.rag.embedding.cache import CachedEmbedder, DiskEmbeddingCache
from app.rag.embedding.factory import get_embedder
from app.rag.embedding.models import EmbeddingConfig, EmbeddingProvider
from app.rag.evaluation.chunking.dataset import GoldenQuestion, load_golden_set
from app.rag.evaluation.chunking.retrieval import (
    BM25Retriever,
    RetrievalEvalSummary,
    evaluate_retrieval,
)
from app.rag.evaluation.embedding.retrieval import DenseRetriever, HybridRetriever
from app.rag.evaluation.embedding.validation import (
    compute_token_divergence_ratio,
    validate_chunks_fit,
)
from app.rag.ingestion.models import ParsedDocument
from app.rag.ingestion.pdf.loader import PDFLoader


PRICE_PER_MILLION_TOKENS: dict[str, float] = {
    "openai/text-embedding-3-small": 0.02,
    "openai/text-embedding-3-large": 0.13,
    "gemini/text-embedding-004": 0.025,
    "local/intfloat/multilingual-e5-small": 0.0,
    "local/baai/bge-m3": 0.0,
    "local": 0.0,
    "fake": 0.0,
}


def get_git_commit_hash() -> str:
    """Return the current short git commit hash and dirty status."""
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


def parse_model_string(model_str: str) -> EmbeddingConfig:
    """Parse a model identifier like 'provider/model[@dimensions]' into an EmbeddingConfig."""
    s = model_str.strip()
    if s.lower() == "fake":
        return EmbeddingConfig(provider=EmbeddingProvider.FAKE, model="deterministic-bow")

    if "/" not in s:
        # Bare name like 'openai' or 'gemini'
        try:
            prov = EmbeddingProvider(s.lower())
            if prov == EmbeddingProvider.OPENAI:
                return EmbeddingConfig(provider=prov, model="text-embedding-3-small")
            elif prov == EmbeddingProvider.GEMINI:
                return EmbeddingConfig(provider=prov, model="text-embedding-004")
            elif prov == EmbeddingProvider.LOCAL:
                return EmbeddingConfig(provider=prov, model="intfloat/multilingual-e5-small")
            else:
                return EmbeddingConfig(provider=prov, model="deterministic-bow")
        except ValueError:
            pass

    parts = s.split("/", 1)
    provider_str = parts[0].strip().lower()
    model_with_dim = parts[1].strip()

    dimensions: int | None = None
    if "@" in model_with_dim:
        m_parts = model_with_dim.split("@", 1)
        model_name = m_parts[0].strip()
        try:
            dimensions = int(m_parts[1].strip())
        except ValueError:
            dimensions = None
    else:
        model_name = model_with_dim

    return EmbeddingConfig(
        provider=EmbeddingProvider(provider_str),
        model=model_name,
        dimensions=dimensions,
    )


def is_provider_available(provider: EmbeddingProvider | str) -> tuple[bool, str]:
    """Check if credentials or requirements exist for the provider."""
    p_str = provider.value if isinstance(provider, EmbeddingProvider) else str(provider)
    if p_str == "openai":
        if not settings.OPENAI_API_KEY:
            return False, "OPENAI_API_KEY environment variable is empty."
    elif p_str == "gemini":
        if not settings.GEMINI_API_KEY:
            return False, "GEMINI_API_KEY environment variable is empty."
    return True, ""


def evaluate_single_model(
    config: EmbeddingConfig,
    all_chunks: list[Chunk],
    questions: list[GoldenQuestion],
    bm25_retriever: BM25Retriever,
    cache: DiskEmbeddingCache,
    tokenizer: TiktokenTokenizer,
    dense_weight: float = 0.5,
) -> dict[str, Any]:
    """Run full evaluation (Dense + Hybrid) for a specific embedding model."""
    embedder = get_embedder(config, cache=cache)
    raw_embedder: Embedder = embedder.inner if isinstance(embedder, CachedEmbedder) else embedder

    # 1. Dokümanları embed et ve indeksleme süresini ölç
    hits_pre_doc = embedder.hits if isinstance(embedder, CachedEmbedder) else 0
    misses_pre_doc = embedder.misses if isinstance(embedder, CachedEmbedder) else 0

    t_start = time.perf_counter()
    dense_retriever = DenseRetriever(embedder)
    dense_retriever.index(all_chunks)
    embed_duration = time.perf_counter() - t_start

    doc_hits = (embedder.hits - hits_pre_doc) if isinstance(embedder, CachedEmbedder) else 0
    doc_misses = (embedder.misses - misses_pre_doc) if isinstance(embedder, CachedEmbedder) else 0

    # 2. Token sayımları ve maliyet hesabı
    total_doc_tokens = sum(tokenizer.count(c.embedding_text) for c in all_chunks)
    total_query_tokens = sum(tokenizer.count(q.question) for q in questions)
    price_key = f"{config.provider}/{config.model}".lower()
    rate = PRICE_PER_MILLION_TOKENS.get(price_key)
    if rate is None:
        rate = PRICE_PER_MILLION_TOKENS.get(str(config.provider).lower(), 0.0)
    est_cost = ((total_doc_tokens + total_query_tokens) / 1_000_000.0) * rate

    # 3. Saf Sorgu Gecikmesi (Uncached Latency): Cache kapalıyken raw embedder ile ölçülür
    uncached_latencies: list[float] = []
    for q in questions:
        t_q0 = time.perf_counter()
        _ = raw_embedder.embed_query(q.question)
        uncached_latencies.append(time.perf_counter() - t_q0)
    avg_query_sec = (
        sum(uncached_latencies) / len(uncached_latencies) if uncached_latencies else 0.0
    )

    # 4. Dense Retrieval Değerlendirmesi
    hits_pre_query = embedder.hits if isinstance(embedder, CachedEmbedder) else 0
    misses_pre_query = embedder.misses if isinstance(embedder, CachedEmbedder) else 0

    dense_summary, dense_details = evaluate_retrieval(
        dense_retriever, questions, all_chunks
    )

    query_hits = (embedder.hits - hits_pre_query) if isinstance(embedder, CachedEmbedder) else 0
    query_misses = (embedder.misses - misses_pre_query) if isinstance(embedder, CachedEmbedder) else 0

    # 5. Hybrid Retrieval Değerlendirmesi
    hybrid_retriever = HybridRetriever(
        dense=dense_retriever,
        bm25=bm25_retriever,
        dense_weight=dense_weight,
    )
    # HybridRetriever her iki retriever'ı bağlar; dense vektörler zaten önbellekte olduğundan hızlıca geçer
    hybrid_summary, hybrid_details = evaluate_retrieval(
        hybrid_retriever, questions, all_chunks
    )

    # 6. Token Limiti ve Token Sapma (Divergence) Oranı Kontrolü
    fit_report = validate_chunks_fit(all_chunks, embedder, tokenizer=tokenizer)
    token_divergence = compute_token_divergence_ratio(
        all_chunks, embedder, tokenizer=tokenizer
    )

    storage_bytes = len(all_chunks) * embedder.dimensions * 4

    return {
        "model_id": embedder.model_id,
        "provider": str(config.provider),
        "model": config.model,
        "dimensions": embedder.dimensions,
        "embed_duration_sec": round(embed_duration, 3),
        "avg_query_sec": round(avg_query_sec, 4),
        "est_cost_usd": round(est_cost, 6),
        "storage_kb": round(storage_bytes / 1024.0, 2),
        "doc_cache_hits": doc_hits,
        "doc_cache_misses": doc_misses,
        "query_cache_hits": query_hits,
        "query_cache_misses": query_misses,
        "token_divergence_ratio": token_divergence,
        "all_chunks_fit": fit_report.all_fit,
        "max_chunk_tokens": fit_report.max_chunk_tokens,
        "dense_summary": dense_summary.model_dump(),
        "hybrid_summary": hybrid_summary.model_dump(),
    }


def generate_markdown_report(
    results: list[dict[str, Any]],
    bm25_summary: RetrievalEvalSummary,
    git_hash: str,
    doc_count: int,
    chunk_count: int,
    question_count: int,
) -> str:
    """Format evaluation results into a comprehensive Markdown report."""
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines: list[str] = []

    lines.append("# 📊 Embedding Model Karşılaştırma ve Benchmark Raporu")
    lines.append("")
    lines.append(f"- **Tarih:** {timestamp}")
    lines.append(f"- **Git Commit:** `{git_hash}`")
    lines.append("- **Tokenizer:** `TiktokenTokenizer (cl100k_base)`")
    lines.append(f"- **Korpus Boyutu:** {doc_count} PDF Dokümanı, {chunk_count} Chunk")
    lines.append(f"- **Golden Set:** {question_count} Test Sorusu (42 soruda her soru ≈ 2.4 puandır)")
    lines.append("")
    lines.append("---")
    lines.append("")

    # 1. Doğruluk Karşılaştırma Tablosu
    lines.append("## 1. Arama Başarısı (Accuracy & Retrieval Quality)")
    lines.append("")
    lines.append(
        "| Model / Arama Yöntemi | Hit@1 | Hit@3 | Hit@5 | MRR | BM25'e Göre Kazanç | Hybrid vs Dense Kazanç |"
    )
    lines.append(
        "|:---|:---:|:---:|:---:|:---:|:---:|:---:|"
    )

    # BM25 Baseline Satırı
    lines.append(
        f"| **BM25 (Baseline)** | %{round(bm25_summary.hit_at_1*100, 1)} | "
        f"%{round(bm25_summary.hit_at_3*100, 1)} | %{round(bm25_summary.hit_at_5*100, 1)} | "
        f"{round(bm25_summary.mrr, 3)} | Baseline | - |"
    )

    all_hit3_scores = [bm25_summary.hit_at_3]

    for res in results:
        dense_s = res["dense_summary"]
        hybrid_s = res["hybrid_summary"]

        all_hit3_scores.append(dense_s["hit_at_3"])
        all_hit3_scores.append(hybrid_s["hit_at_3"])

        # Dense Satırı
        bm25_diff_dense = round((dense_s["hit_at_3"] - bm25_summary.hit_at_3) * 100, 1)
        diff_str_dense = f"{'+' if bm25_diff_dense > 0 else ''}{bm25_diff_dense}%"
        if abs(bm25_diff_dense) < 5.0:
            diff_str_dense = f"≈ {diff_str_dense}"

        lines.append(
            f"| `{res['model_id']}` (Dense) | %{round(dense_s['hit_at_1']*100, 1)} | "
            f"%{round(dense_s['hit_at_3']*100, 1)} | %{round(dense_s['hit_at_5']*100, 1)} | "
            f"{round(dense_s['mrr'], 3)} | {diff_str_dense} | - |"
        )

        # Hybrid Satırı
        bm25_diff_hyb = round((hybrid_s["hit_at_3"] - bm25_summary.hit_at_3) * 100, 1)
        diff_str_hyb = f"{'+' if bm25_diff_hyb > 0 else ''}{bm25_diff_hyb}%"
        if abs(bm25_diff_hyb) < 5.0:
            diff_str_hyb = f"≈ {diff_str_hyb}"

        hyb_vs_dense = round((hybrid_s["hit_at_3"] - dense_s["hit_at_3"]) * 100, 1)
        hyb_vs_dense_str = f"{'+' if hyb_vs_dense > 0 else ''}{hyb_vs_dense}%"
        if abs(hyb_vs_dense) < 5.0:
            hyb_vs_dense_str = f"≈ {hyb_vs_dense_str}"

        lines.append(
            f"| `{res['model_id']}` (Hybrid) | %{round(hybrid_s['hit_at_1']*100, 1)} | "
            f"%{round(hybrid_s['hit_at_3']*100, 1)} | %{round(hybrid_s['hit_at_5']*100, 1)} | "
            f"{round(hybrid_s['mrr'], 3)} | {diff_str_hyb} | **{hyb_vs_dense_str}** |"
        )

    lines.append("")

    # Korpus Doygunluk Kontrolü (Tüm modellerde Hit@3 >= 95% mi?)
    is_saturated = all(score >= 0.95 for score in all_hit3_scores)
    if is_saturated:
        lines.append(
            "> [!WARNING]\n"
            "> **Korpus Doygunluk Uyarısı (Saturation):** Tüm modellerde ve baseline'da `Hit@3` ≈ %100 seviyesindedir. "
            "Mevcut küçük korpus modeller arasındaki ayrımı net gösterememektedir; 5 puandan küçük farklar istatistiksel "
            "gürültü sınırındadır. Gerçek büyük korpus geldiğinde Adım 8 yeniden koşturulmalıdır.\n"
        )

    # 2. Operasyonel Metrikler Tablosu
    lines.append("## 2. Operasyonel ve Maliyet Metrikleri")
    lines.append("")
    lines.append(
        "| Model | Boyut (dim) | Bellek / Disk (KB) | Embed Süresi (sn) | Saf Sorgu Gecikmesi (sn) | Tahmini Maliyet ($) | Önbellek (Doc Hits/Miss - Query Hits/Miss) | Token Sapma Oranı (cl100k/Model) |"
    )
    lines.append(
        "|:---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|"
    )

    for res in results:
        cache_str = f"Doc: {res['doc_cache_hits']}/{res['doc_cache_misses']} - Query: {res['query_cache_hits']}/{res['query_cache_misses']}"
        div_str = (
            f"{res['token_divergence_ratio']:.3f}"
            if res.get("token_divergence_ratio") is not None
            else "N/A"
        )
        lines.append(
            f"| `{res['model_id']}` | {res['dimensions']} | {res['storage_kb']} KB | "
            f"{res['embed_duration_sec']} sn | {res['avg_query_sec']} sn | "
            f"${res['est_cost_usd']} | {cache_str} | {div_str} |"
        )

    lines.append("")
    lines.append("---")
    lines.append("")

    # 3. Kategori Bazlı Kırılım
    lines.append("## 3. Kategori Bazlı Hit@3 Başarısı")
    lines.append("")

    # Sütun başlıkları
    cat_keys = sorted(bm25_summary.category_hit3.keys())
    cat_header = " | ".join(cat_keys)
    cat_sep = " | ".join([":---:"] * len(cat_keys))
    lines.append(f"| Model | {cat_header} |")
    lines.append(f"|:---|{cat_sep}|")

    bm25_cat_vals = " | ".join([f"%{round(bm25_summary.category_hit3.get(k, 0.0)*100, 1)}" for k in cat_keys])
    lines.append(f"| **BM25** | {bm25_cat_vals} |")

    for res in results:
        dense_cat = res["dense_summary"]["category_hit3"]
        d_vals = " | ".join([f"%{round(dense_cat.get(k, 0.0)*100, 1)}" for k in cat_keys])
        lines.append(f"| `{res['model_id']}` (Dense) | {d_vals} |")

        hyb_cat = res["hybrid_summary"]["category_hit3"]
        h_vals = " | ".join([f"%{round(hyb_cat.get(k, 0.0)*100, 1)}" for k in cat_keys])
        lines.append(f"| `{res['model_id']}` (Hybrid) | {h_vals} |")

    lines.append("")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Embedding model comparison runner.")
    parser.add_argument(
        "--models",
        type=str,
        default="openai/text-embedding-3-small,gemini/text-embedding-004,fake/deterministic-bow",
        help="Comma-separated models, e.g. openai/text-embedding-3-small,fake/deterministic-bow",
    )
    parser.add_argument(
        "--docs-dir",
        type=Path,
        default=Path("eval/chunking/docs"),
        help="Path to directory containing PDF documents",
    )
    parser.add_argument(
        "--golden",
        type=Path,
        default=Path("eval/chunking/golden_set.json"),
        help="Path to golden set JSON file",
    )
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=Path("eval/embedding/cache"),
        help="Directory to store SQLite embedding cache",
    )
    parser.add_argument(
        "--reports-dir",
        type=Path,
        default=Path("eval/embedding/reports"),
        help="Directory to save generated evaluation reports",
    )
    parser.add_argument(
        "--dense-weight",
        type=float,
        default=0.5,
        help="Weight for dense retrieval in hybrid search (0.0 to 1.0)",
    )

    args = parser.parse_args()

    # 1. Dokümanları ve Soruları Yükle
    if not args.docs_dir.exists():
        print(f"[HATA] Doküman dizini bulunamadı: {args.docs_dir}")
        return

    pdf_files = sorted(args.docs_dir.glob("*.pdf"))
    if not pdf_files:
        print(f"[HATA] {args.docs_dir} içinde PDF dokümanı bulunamadı!")
        return

    loader = PDFLoader()
    documents = [loader.load(p) for p in pdf_files]
    questions = load_golden_set(args.golden)
    tokenizer = TiktokenTokenizer()
    git_hash = get_git_commit_hash()

    # 2. Standart Chunking (DefaultChunker, Structure-Aware, max_tokens=300)
    chunker = DefaultChunker(tokenizer=tokenizer, config=ChunkingConfig())
    all_chunks: list[Chunk] = []
    for doc in documents:
        all_chunks.extend(chunker.chunk(doc))

    print(f"[*] {len(documents)} PDF dokümanı yüklendi.")
    print(f"[*] {len(all_chunks)} chunk oluşturuldu (DefaultChunker).")
    print(f"[*] {len(questions)} Golden soru yüklendi.")

    # 3. BM25 Baseline Değerlendirmesi
    print("[*] BM25 baseline çalıştırılıyor...")
    bm25_retriever = BM25Retriever()
    bm25_summary, _ = evaluate_retrieval(bm25_retriever, questions, all_chunks)
    print(f"[+] BM25 Baseline Tamamlandı: Hit@1=%{round(bm25_summary.hit_at_1*100, 1)}, Hit@3=%{round(bm25_summary.hit_at_3*100, 1)}, MRR={round(bm25_summary.mrr, 3)}")

    # 4. Modelleri Değerlendir
    model_strings = [m.strip() for m in args.models.split(",") if m.strip()]
    cache_file = args.cache_dir / "embeddings.db"
    cache = DiskEmbeddingCache(cache_file)

    results: list[dict[str, Any]] = []

    for m_str in model_strings:
        config = parse_model_string(m_str)
        available, reason = is_provider_available(config.provider)
        if not available:
            print(f"[UYARI] '{m_str}' atlanıyor: {reason}")
            continue

        print(f"[*] Model değerlendiriliyor: {config.model_id()}...")
        try:
            res = evaluate_single_model(
                config=config,
                all_chunks=all_chunks,
                questions=questions,
                bm25_retriever=bm25_retriever,
                cache=cache,
                tokenizer=tokenizer,
                dense_weight=args.dense_weight,
            )
            results.append(res)
            print(
                f"[+] {config.model_id()} Tamamlandı! "
                f"Dense Hit@3: %{round(res['dense_summary']['hit_at_3']*100, 1)} | "
                f"Hybrid Hit@3: %{round(res['hybrid_summary']['hit_at_3']*100, 1)} | "
                f"Süre: {res['embed_duration_sec']}s"
            )
        except Exception as exc:
            print(f"[HATA] {config.model_id()} çalıştırılırken hata: {exc}")

    if not results:
        print("[!] Hiçbir model değerlendirilemedi. Lütfen geçerli bir model veya '--models fake' belirtin.")
        return

    # 5. Rapor Üret
    args.reports_dir.mkdir(parents=True, exist_ok=True)
    today_str = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    report_slug = f"eval-embedding-{today_str}"

    md_content = generate_markdown_report(
        results=results,
        bm25_summary=bm25_summary,
        git_hash=git_hash,
        doc_count=len(documents),
        chunk_count=len(all_chunks),
        question_count=len(questions),
    )

    md_path = args.reports_dir / f"{report_slug}.md"
    json_path = args.reports_dir / f"{report_slug}.json"

    md_path.write_text(md_content, encoding="utf-8")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "timestamp": today_str,
                "git_commit": git_hash,
                "bm25_summary": bm25_summary.model_dump(),
                "models": results,
            },
            f,
            ensure_ascii=False,
            indent=2,
        )

    print("\n" + "=" * 60)
    print(f"🎉 Rapor başarıyla üretildi!")
    print(f"📄 Markdown Rapor: {md_path}")
    print(f"📊 JSON Rapor:     {json_path}")
    print("=" * 60)


if __name__ == "__main__":
    main()
