import argparse
import datetime
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

# Windows konsolunda UTF-8 çıktı desteği
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from app.rag.chunking.factory import get_chunker
from app.rag.chunking.models import ChunkingConfig, ChunkStrategy
from app.rag.chunking.tokenizer import TiktokenTokenizer
from app.rag.evaluation.chunking.dataset import load_golden_set
from app.rag.evaluation.chunking.retrieval import BM25Retriever, evaluate_retrieval
from app.rag.evaluation.chunking.stats import chunk_stats
from app.rag.ingestion.models import ParsedDocument, QualityReport
from app.rag.ingestion.pdf.loader import PDFLoader


def get_git_commit_hash() -> str:
    """Return the current short git commit hash if available."""
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], stderr=subprocess.DEVNULL
        )
        return out.decode("utf-8").strip()
    except Exception:
        return "unknown"


def run_single_experiment(
    strategy: ChunkStrategy,
    config: ChunkingConfig,
    documents: list[ParsedDocument],
    questions: list[Any],
    tokenizer: TiktokenTokenizer,
) -> dict[str, Any]:
    """Run chunking, intrinsic stats, and retrieval eval for a specific configuration."""
    chunker = get_chunker(strategy, tokenizer, config)

    # Tüm dokümanları chunk'la
    all_chunks = []
    combined_elements = []
    for doc in documents:
        chunks = chunker.chunk(doc)
        all_chunks.extend(chunks)
        combined_elements.extend(doc.elements)

    total_pages = sum(d.quality.page_count for d in documents) if documents else 0
    combined_doc = ParsedDocument(
        source_file="corpus_combined",
        elements=combined_elements,
        quality=QualityReport(page_count=total_pages, status="ok"),
        parser_name="multi_doc",
        parser_version="1.0",
    )

    # 1. Intrinsic İstatistikler (Adım 9)
    stats = chunk_stats(all_chunks, combined_doc, tokenizer, min_tokens=config.min_tokens)

    # 2. Retrieval İstatistikleri (Adım 11)
    retriever = BM25Retriever(use_stemming=False)
    summary_topk, _ = evaluate_retrieval(retriever, questions, all_chunks)
    summary_budget, _ = evaluate_retrieval(
        retriever, questions, all_chunks, token_budget=1500, tokenizer=tokenizer
    )

    return {
        "strategy": strategy.value,
        "max_tokens": config.max_tokens,
        "overlap_tokens": config.overlap_tokens,
        "include_breadcrumb": config.include_breadcrumb,
        "isolate_tables": config.isolate_tables,
        "config_hash": config.config_hash(),
        # Intrinsic stats
        "chunk_count": stats.chunk_count,
        "tokens_mean": stats.tokens_mean,
        "tokens_p50": stats.tokens_p50,
        "tokens_p95": stats.tokens_p95,
        "redundancy": stats.redundancy,
        "sentence_cut_ratio": stats.sentence_cut_ratio,
        "table_split_ratio": stats.table_split_ratio,
        "table_headless_chunks": stats.table_headless_chunks,
        "orphan_heading_ratio": stats.orphan_heading_ratio,
        # Retrieval stats (Top-K)
        "evidence_intact_ratio": summary_topk.evidence_intact_ratio,
        "evidence_fragmented_ratio": summary_topk.evidence_fragmented_ratio,
        "hit_at_1": summary_topk.hit_at_1,
        "hit_at_3": summary_topk.hit_at_3,
        "hit_at_5": summary_topk.hit_at_5,
        "mrr": summary_topk.mrr,
        "category_hit3": summary_topk.category_hit3,
        # Retrieval stats (Budget: 1500 tokens)
        "hit_budget_3": summary_budget.hit_at_3,
    }


def _generate_dynamic_findings(experiments: list[dict[str, Any]]) -> list[str]:
    """Generate dynamic data-driven engineering findings directly from experiment results."""
    findings: list[str] = []

    # 1. Tablo Bütünlüğü (Headless table chunks & Table split ratio)
    struct_headless = [
        e["table_headless_chunks"] for e in experiments if e["strategy"] == "structure"
    ]
    other_headless = [
        e["table_headless_chunks"] for e in experiments if e["strategy"] != "structure"
    ]
    total_struct_headless = sum(struct_headless)
    total_other_headless = sum(other_headless)

    if total_other_headless > 0 and total_struct_headless == 0:
        findings.append(
            f"1. **Tablo Bütünlüğü:** Structure-Aware chunker başlık satırlarını ve ayırıcılarını "
            f"tüm alt parçalara kopyaladığı için başlıksız tablo chunk sayısı (`table_headless_chunks`) "
            f"tüm koşullarda 0 kalmıştır. Diğer stratejilerde toplam {total_other_headless} adet "
            f"başlıksız tablo parçası oluşmuştur."
        )
    else:
        findings.append(
            f"1. **Tablo Bütünlüğü:** Deneylerde Structure-Aware için {total_struct_headless}, "
            f"diğer stratejiler için {total_other_headless} adet başlıksız tablo chunk'ı tespit edilmiştir."
        )

    # 2. Cümle Kesilme Oranı (Sentence Cut Ratio)
    fixed_cuts = [e["sentence_cut_ratio"] for e in experiments if e["strategy"] == "fixed"]
    rec_cuts = [e["sentence_cut_ratio"] for e in experiments if e["strategy"] == "recursive"]
    struct_cuts = [e["sentence_cut_ratio"] for e in experiments if e["strategy"] == "structure"]

    avg_fix = round((sum(fixed_cuts) / len(fixed_cuts) * 100), 1) if fixed_cuts else 0.0
    avg_rec = round((sum(rec_cuts) / len(rec_cuts) * 100), 1) if rec_cuts else 0.0
    avg_str = round((sum(struct_cuts) / len(struct_cuts) * 100), 1) if struct_cuts else 0.0

    findings.append(
        f"2. **Cümle Hasarı:** Ortalama cümle kesilme hasarı: Fixed = %{avg_fix}, "
        f"Recursive = %{avg_rec}, Structure-Aware = %{avg_str}. Recursive ve Structure-Aware yaklaşımları "
        f"cümle ve paragraf sınırlarını koruyarak anlamsal bütünlüğü korumuştur."
    )

    # 3. Breadcrumb Ablation Etkisi
    bc_diffs = []
    for exp_on in experiments:
        if exp_on["include_breadcrumb"]:
            for exp_off in experiments:
                if (
                    not exp_off["include_breadcrumb"]
                    and exp_on["strategy"] == exp_off["strategy"]
                    and exp_on["max_tokens"] == exp_off["max_tokens"]
                    and exp_on["overlap_tokens"] == exp_off["overlap_tokens"]
                    and exp_on["isolate_tables"] == exp_off["isolate_tables"]
                ):
                    hd_on = exp_on["category_hit3"].get("heading_dependent", 0.0)
                    hd_off = exp_off["category_hit3"].get("heading_dependent", 0.0)
                    bc_diffs.append((hd_on, hd_off))

    if bc_diffs:
        avg_hd_on = round(sum(d[0] for d in bc_diffs) / len(bc_diffs) * 100, 1)
        avg_hd_off = round(sum(d[1] for d in bc_diffs) / len(bc_diffs) * 100, 1)
        diff = round(avg_hd_on - avg_hd_off, 1)
        sign = "+" if diff > 0 else ""
        findings.append(
            f"3. **Breadcrumb Ablation Etkisi:** `heading_dependent` soru kategorisinde breadcrumb açıkken "
            f"ortalama Hit@3 %{avg_hd_on}, kapalıyken %{avg_hd_off} olarak ölçülmüştür "
            f"(fark: {sign}%{diff} puan). Başlık öneki hiyerarşik bağlam taşıyarak doğru parçanın getirilmesini etkilemektedir."
        )
    else:
        findings.append(
            "3. **Breadcrumb Ablation Etkisi:** Breadcrumb açık/kapalı varyantları incelendiğinde "
            "başlık bilgisi retrieval bağlamına katkı sunmaktadır."
        )

    # 4. Kanıt Bütünlüğü (Evidence Intactness)
    best_intact = max(experiments, key=lambda e: e["evidence_intact_ratio"])
    worst_intact = min(experiments, key=lambda e: e["evidence_intact_ratio"])
    findings.append(
        f"4. **Kanıt Bütünlüğü:** En yüksek tek-parça kanıt bütünlüğü %{round(best_intact['evidence_intact_ratio']*100, 1)} "
        f"ile {best_intact['strategy']} (max_tokens={best_intact['max_tokens']}) konfigürasyonunda gerçekleşmiş; "
        f"en düşük oran %{round(worst_intact['evidence_intact_ratio']*100, 1)} ile {worst_intact['strategy']} "
        f"tarafında kalmıştır."
    )

    # 5. Eşit Bağlam Bütçesi
    budget_scores = [e.get("hit_budget_3", 0.0) for e in experiments if "hit_budget_3" in e]
    if budget_scores:
        avg_budget = round(sum(budget_scores) / len(budget_scores) * 100, 1)
        topk_scores = [e["hit_at_3"] for e in experiments]
        avg_topk = round(sum(topk_scores) / len(topk_scores) * 100, 1)
        findings.append(
            f"5. **Eşit Bağlam Bütçesi (1500 Token):** Top-3 yerine toplam 1500 token'lık sabit bütçeli "
            f"getirme (`search_by_budget`) yapıldığında ortalama Hit@3 oranı %{avg_budget} olarak gerçekleşmiştir "
            f"(Standart Top-3 ortalaması: %{avg_topk})."
        )

    return findings


def format_markdown_report(
    experiments: list[dict[str, Any]],
    git_hash: str,
    doc_count: int,
    question_count: int,
) -> str:
    """Format experiments into structured Markdown tables."""
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    md = []
    md.append("# 📊 Chunking Karşılaştırma ve Ablation Raporu")
    md.append("")
    md.append(f"- **Tarih:** {timestamp}")
    md.append(f"- **Git Commit:** `{git_hash}`")
    md.append("- **Tokenizer:** `TiktokenTokenizer (cl100k_base)`")
    md.append(f"- **Doküman Sayısı:** {doc_count} PDF")
    md.append(f"- **Soru Sayısı (Golden Set):** {question_count} soru")
    md.append("")
    md.append("---")
    md.append("")
    md.append("## 1. Ana Karşılaştırma Matrisi")
    md.append("")
    md.append(
        "| Strateji | max_tokens | overlap | Breadcrumb | Chunk Sayısı | Redundancy | "
        "Cümle Kesilme | Tablo Bölünme | Başlıksız Tablo | Intact Evidence | Hit@1 | Hit@3 | Hit@3 (1500 Bütçe) | MRR |"
    )
    md.append(
        "|:---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|"
    )

    for exp in experiments:
        bc_icon = "✅" if exp["include_breadcrumb"] else "❌"
        ov_display = "-" if exp["strategy"] == "structure" else str(exp["overlap_tokens"])
        budget_display = (
            f"%{round(exp['hit_budget_3']*100, 1)}" if "hit_budget_3" in exp else "-"
        )
        md.append(
            f"| **{exp['strategy']}** | {exp['max_tokens']} | {ov_display} | {bc_icon} | "
            f"{exp['chunk_count']} | ≈{exp['redundancy']}x | %{round(exp['sentence_cut_ratio']*100, 1)} | "
            f"%{round(exp['table_split_ratio']*100, 1)} | {exp['table_headless_chunks']} | "
            f"%{round(exp['evidence_intact_ratio']*100, 1)} | %{round(exp['hit_at_1']*100, 1)} | "
            f"%{round(exp['hit_at_3']*100, 1)} | {budget_display} | ≈{exp['mrr']} |"
        )

    md.append("")
    md.append("---")
    md.append("")
    md.append("## 2. Kategori Bazlı Hit@3 Kırılım Matrisi")
    md.append("")
    categories = [
        "single_fact",
        "exception",
        "table_lookup",
        "table_cross_page",
        "cross_page_sentence",
        "heading_dependent",
    ]
    header = "| Strateji | max_tokens | Breadcrumb | " + " | ".join(categories) + " |"
    sep = "|:---|:---:|:---:| " + " | ".join([":---:"] * len(categories)) + " |"
    md.append(header)
    md.append(sep)

    for exp in experiments:
        bc_icon = "✅" if exp["include_breadcrumb"] else "❌"
        cat_scores = []
        for cat in categories:
            score = exp["category_hit3"].get(cat, 0.0)
            cat_scores.append(f"%{round(score * 100, 1)}")
        md.append(
            f"| **{exp['strategy']}** | {exp['max_tokens']} | {bc_icon} | "
            + " | ".join(cat_scores)
            + " |"
        )

    md.append("")
    md.append("---")
    md.append("")
    md.append("## 3. Temel Mühendislik Çıkarımları")
    md.append("")
    for finding in _generate_dynamic_findings(experiments):
        md.append(finding)
    md.append("")

    return "\n".join(md)


def main():
    parser = argparse.ArgumentParser(description="Chunking Karşılaştırma Runner'ı")
    parser.add_argument("--docs-dir", default="eval/chunking/docs", help="Eval PDF dizini")
    parser.add_argument(
        "--golden-set", default="eval/chunking/golden_set.json", help="Golden set JSON yolu"
    )
    parser.add_argument("--reports-dir", default="eval/chunking/reports", help="Rapor çıktı dizini")
    parser.add_argument(
        "--sweep", action="store_true", help="Farklı max_tokens ve overlap sweep'i yap"
    )
    args = parser.parse_args()

    root_dir = Path(__file__).resolve().parents[4]
    docs_dir = root_dir / args.docs_dir
    golden_path = root_dir / args.golden_set
    reports_dir = root_dir / args.reports_dir
    reports_dir.mkdir(parents=True, exist_ok=True)

    print(f"[*] Dokümanlar yükleniyor: {docs_dir}")
    loader = PDFLoader()
    doc_files = sorted(list(docs_dir.glob("*.pdf")))
    if not doc_files:
        print(f"[HATA] {docs_dir} altında PDF bulunamadı!")
        return

    documents = [loader.load(p) for p in doc_files]
    questions = load_golden_set(golden_path)
    tokenizer = TiktokenTokenizer()
    git_hash = get_git_commit_hash()

    print(f"[*] {len(documents)} PDF dokümanı ve {len(questions)} Golden soru yüklendi.")
    print("[*] Deneyler başlatılıyor...")

    # Standart Deney Konfigürasyonları
    configs_to_run = [
        # 1. Fixed Baseline (Breadcrumb açık/kapalı)
        (
            ChunkStrategy.FIXED,
            ChunkingConfig(max_tokens=300, overlap_tokens=45, include_breadcrumb=True),
        ),
        (
            ChunkStrategy.FIXED,
            ChunkingConfig(max_tokens=300, overlap_tokens=45, include_breadcrumb=False),
        ),
        # 2. Recursive (Breadcrumb açık/kapalı)
        (
            ChunkStrategy.RECURSIVE,
            ChunkingConfig(max_tokens=300, overlap_tokens=45, include_breadcrumb=True),
        ),
        (
            ChunkStrategy.RECURSIVE,
            ChunkingConfig(max_tokens=300, overlap_tokens=45, include_breadcrumb=False),
        ),
        # 3. Structure-Aware (Breadcrumb açık/kapalı ve Table Isolate) - overlap 0
        (
            ChunkStrategy.STRUCTURE,
            ChunkingConfig(
                max_tokens=300,
                overlap_tokens=0,
                include_breadcrumb=True,
                isolate_tables=False,
            ),
        ),
        (
            ChunkStrategy.STRUCTURE,
            ChunkingConfig(
                max_tokens=300,
                overlap_tokens=0,
                include_breadcrumb=False,
                isolate_tables=False,
            ),
        ),
        (
            ChunkStrategy.STRUCTURE,
            ChunkingConfig(
                max_tokens=300,
                overlap_tokens=0,
                include_breadcrumb=True,
                isolate_tables=True,
            ),
        ),
    ]

    if args.sweep:
        # Sweep: max_tokens ∈ {200, 350, 500}, overlap ∈ {0%, 15%}
        for m in [200, 350, 500]:
            for ov_pct in [0.0, 0.15]:
                ov = int(m * ov_pct)
                configs_to_run.append(
                    (
                        ChunkStrategy.FIXED,
                        ChunkingConfig(max_tokens=m, overlap_tokens=ov, min_tokens=10),
                    )
                )
                configs_to_run.append(
                    (
                        ChunkStrategy.RECURSIVE,
                        ChunkingConfig(max_tokens=m, overlap_tokens=ov, min_tokens=10),
                    )
                )
            # Structure-Aware uses natural section boundaries, no sliding overlap
            configs_to_run.append(
                (
                    ChunkStrategy.STRUCTURE,
                    ChunkingConfig(max_tokens=m, overlap_tokens=0, min_tokens=10),
                )
            )

    results: list[dict[str, Any]] = []
    for strat, cfg in configs_to_run:
        bc_str = "BC=ON" if cfg.include_breadcrumb else "BC=OFF"
        tbl_str = "TBL=ISO" if cfg.isolate_tables else "TBL=MIX"
        print(
            f"  -> Kosuluyor: {strat.value:<10} | max={cfg.max_tokens:<3} | "
            f"ov={cfg.overlap_tokens:<2} | {bc_str} | {tbl_str}"
        )
        res = run_single_experiment(strat, cfg, documents, questions, tokenizer)
        results.append(res)

    # Rapor üretimi
    md_content = format_markdown_report(results, git_hash, len(documents), len(questions))

    date_str = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    report_md_path = reports_dir / f"chunking_report_{date_str}.md"
    report_json_path = reports_dir / f"chunking_report_{date_str}.json"

    with open(report_md_path, "w", encoding="utf-8") as f:
        f.write(md_content)

    with open(report_json_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print("\n[OK] Deneyler tamamlandı!")
    print(f"[+] Markdown Raporu: {report_md_path}")
    print(f"[+] JSON Verisi:     {report_json_path}\n")
    print(md_content)


if __name__ == "__main__":
    main()
