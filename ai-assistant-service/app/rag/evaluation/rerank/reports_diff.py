"""CLI tool to compare two RAG generation evaluation JSON reports (A vs B) with fairness verification and flip analysis."""

from __future__ import annotations

import argparse
import datetime
import json
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


def check_fairness(meta_a: dict[str, Any], meta_b: dict[str, Any], count_a: int, count_b: int) -> list[str]:
    """İki koşunun adil (fair) bir karşılaştırma olup olmadığını doğrular."""
    warnings: list[str] = []

    fairness_fields = [
        ("embedder", "Embedder modeli"),
        ("llm_provider", "LLM Sağlayıcısı"),
        ("llm_model", "LLM Modeli"),
        ("retrieval_mode", "Retrieval Modu (dense/sparse/hybrid)"),
        ("min_dense_score", "Min Dense Skoru (Abstain Eşiği)"),
        ("top_k", "Top-K Arama Parametresi"),
        ("token_budget", "Token Bütçesi"),
    ]

    for key, label in fairness_fields:
        val_a = meta_a.get(key)
        val_b = meta_b.get(key)
        if val_a != val_b:
            warnings.append(f"{label} farklı: A='{val_a}' vs B='{val_b}'")

    rerank_a = meta_a.get("rerank")
    rerank_b = meta_b.get("rerank")
    if rerank_a and rerank_b and rerank_a == rerank_b:
        warnings.append(
            f"Reranker ayarı her iki raporda da aynı (A='{rerank_a}', B='{rerank_b}'). Biri 'off' diğeri 'on' olmalıdır."
        )

    if count_a != count_b:
        warnings.append(f"Toplam soru sayısı farklı: A={count_a} vs B={count_b}")

    commit_a = meta_a.get("git_commit")
    commit_b = meta_b.get("git_commit")
    if commit_a and commit_b and commit_a != commit_b:
        warnings.append(f"Git commit farklı: A=`{commit_a}` vs B=`{commit_b}`")

    return warnings


def analyze_generation_flips(results_a: list[dict[str, Any]], results_b: list[dict[str, Any]]) -> dict[str, Any]:
    """A ve B raporları arasındaki soru bazlı doğruluk ve halüsinasyon değişimlerini analiz eder."""
    map_a = {r["case_id"]: r for r in results_a}
    map_b = {r["case_id"]: r for r in results_b}

    common_ids = sorted(set(map_a.keys()).intersection(map_b.keys()))

    improved: list[dict[str, Any]] = []
    regressed: list[dict[str, Any]] = []
    new_hallucinations: list[dict[str, Any]] = []
    unchanged_count = 0

    for cid in common_ids:
        ra = map_a[cid]
        rb = map_b[cid]

        ca = ra.get("correct", False)
        cb = rb.get("correct", False)

        is_answerable = ra.get("answerable", True)

        # Halüsinasyon analizi: Cevaplanamaz bir soru A'da abstain iken B'de answered olmuşsa
        if not is_answerable:
            if ra.get("status") == "abstained" and rb.get("status") == "answered":
                new_hallucinations.append({
                    "id": cid,
                    "question": ra.get("question"),
                    "answer_b": rb.get("answer_text"),
                })

        if not ca and cb:
            improved.append({
                "id": cid,
                "question": ra.get("question"),
                "status_a": ra.get("status"),
                "status_b": rb.get("status"),
            })
        elif ca and not cb:
            regressed.append({
                "id": cid,
                "question": ra.get("question"),
                "status_a": ra.get("status"),
                "status_b": rb.get("status"),
            })
        else:
            unchanged_count += 1

    return {
        "improved": improved,
        "regressed": regressed,
        "new_hallucinations": new_hallucinations,
        "unchanged_count": unchanged_count,
    }


def generate_diff_report(
    report_a_path: str,
    report_b_path: str,
    data_a: dict[str, Any],
    data_b: dict[str, Any],
    output_dir: Path | None = None,
) -> str:
    """İki generation raporunun karşılaştırma Markdown dokümanını üretir."""
    meta_a = data_a.get("meta", {})
    meta_b = data_b.get("meta", {})
    sum_a = data_a.get("summary", {})
    sum_b = data_b.get("summary", {})
    res_a = data_a.get("results", [])
    res_b = data_b.get("results", [])

    fairness_warnings = check_fairness(meta_a, meta_b, len(res_a), len(res_b))
    flips = analyze_generation_flips(res_a, res_b)

    lines: list[str] = []
    lines.append("# RAG Generation Karşılaştırma Raporu (A/B Diff)\n")
    lines.append(f"- **Rapor A (Referans):** `{report_a_path}`")
    lines.append(f"  - Reranker: `{meta_a.get('rerank', 'unknown')}` ({meta_a.get('reranker_id', 'none')})")
    lines.append(f"- **Rapor B (Karşılaştırılan):** `{report_b_path}`")
    lines.append(f"  - Reranker: `{meta_b.get('rerank', 'unknown')}` ({meta_b.get('reranker_id', 'none')})")
    lines.append(f"- **Tarih:** `{datetime.datetime.now().isoformat()}`\n")

    # Adalet Uyarısı
    if fairness_warnings:
        lines.append("> [!WARNING]")
        lines.append("> **KARŞILAŞTIRMA ADİL DEĞİL (UNFAIR COMPARISON):**")
        for w in fairness_warnings:
            lines.append(f"> - {w}")
        lines.append("> Sonuçlardaki farklar yalnızca reranker'dan değil, bu değişkenlerden kaynaklanıyor olabilir!\n")

    # Kırmızı Bayrak: Yeni Halüsinasyon
    if flips["new_hallucinations"]:
        lines.append("> [!CAUTION]")
        lines.append(f"> **🔴 KIRMIZI BAYRAK: {len(flips['new_hallucinations'])} YENİ HALÜSİNASYON TESPİT EDİLDİ!**")
        lines.append("> Daha önce güvenle abstain edilen cevaplanamaz sorularda B koşusunda uydurma cevap üretildi:")
        for h in flips["new_hallucinations"]:
            lines.append(f"> - `[{h['id']}]` {h['question']} -> Cevap: *\"{h['answer_b']}\"*")
        lines.append("")

    # Metrik Karşılaştırma Tablosu
    lines.append("## 1. Temel Metrikler Karşılaştırması\n")
    lines.append("| Metrik | Rapor A | Rapor B | Fark (Δ) |")
    lines.append("| :--- | :--- | :--- | :--- |")

    metrics_to_compare = [
        ("answer_accuracy", "Cevap Doğruluğu (Accuracy)", "%", 100),
        ("false_abstain_rate", "Yanlış Abstain Oranı", "%", 100),
        ("hallucination_rate", "Halüsinasyon Oranı", "%", 100),
        ("retry_rate", "Retry Oranı", "%", 100),
        ("avg_input_tokens", "Ortalama Girdi Token", " token", 1),
        ("latency_p50_ms", "Gecikme p50 (ms)", " ms", 1),
        ("latency_p95_ms", "Gecikme p95 (ms)", " ms", 1),
    ]

    for key, label, unit, multiplier in metrics_to_compare:
        val_a = sum_a.get(key, 0.0) * multiplier
        val_b = sum_b.get(key, 0.0) * multiplier
        diff = val_b - val_a
        sign = "+" if diff > 0 else ""

        lines.append(f"| **{label}** | {val_a:.2f}{unit} | {val_b:.2f}{unit} | {sign}{diff:.2f}{unit} |")
    lines.append("")

    # Flip Analizi Bölümü
    total_flips = len(flips["improved"]) + len(flips["regressed"])
    lines.append("## 2. Soru Bazında Değişim (Flip Analizi)\n")
    lines.append(f"- **Düzelen Soru Sayısı:** {len(flips['improved'])}")
    lines.append(f"- **Bozulan Soru Sayısı:** {len(flips['regressed'])}")
    lines.append(f"- **Değişmeyen Soru Sayısı:** {flips['unchanged_count']}\n")

    if total_flips <= 2:
        lines.append(
            f"> [!NOTE]\n"
            f"> **GÜRÜLTÜ UYARISI:** Toplam değişim sayısı {total_flips} <= 2 soru. "
            f"Sıcaklık 0 olsa dahi LLM çıktılarındaki dalgalanmalar nedeniyle bu fark model gürültüsü (noise) olabilir; "
            f"nihai karardan önce koşuyu tekrarlamanız önerilir.\n"
        )

    if flips["improved"]:
        lines.append("### 🟢 Düzelen Sorular (A: Yanlış -> B: Doğru)")
        for item in flips["improved"]:
            lines.append(f"- `[{item['id']}]`: {item['question']} (`{item['status_a']} -> {item['status_b']}`)")
        lines.append("")

    if flips["regressed"]:
        lines.append("### 🔴 Bozulan Sorular (A: Doğru -> B: Yanlış)")
        for item in flips["regressed"]:
            lines.append(f"- `[{item['id']}]`: {item['question']} (`{item['status_a']} -> {item['status_b']}`)")
        lines.append("")

    report_text = "\n".join(lines)

    if output_dir:
        output_dir.mkdir(parents=True, exist_ok=True)
        out_name = f"diff-{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}-{uuid.uuid4().hex[:6]}.md"
        out_path = output_dir / out_name
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(report_text)
        print(f"[✓] Diff raporu kaydedildi: {out_path}")

    return report_text


def main() -> None:
    parser = argparse.ArgumentParser(description="Generation Raporları A/B Karşılaştırıcısı")
    parser.add_argument("report_a", type=Path, help="A Raporu (JSON yolu - referans / rerank kapalı)")
    parser.add_argument("report_b", type=Path, help="B Raporu (JSON yolu - rerank açık)")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("eval/rerank/reports"),
        help="Diff Markdown raporunun yazılacağı dizin",
    )

    args = parser.parse_args()

    if not args.report_a.is_file():
        print(f"[HATA] Rapor A bulunamadı: {args.report_a}")
        sys.exit(1)
    if not args.report_b.is_file():
        print(f"[HATA] Rapor B bulunamadı: {args.report_b}")
        sys.exit(1)

    with open(args.report_a, encoding="utf-8") as f:
        data_a = json.load(f)
    with open(args.report_b, encoding="utf-8") as f:
        data_b = json.load(f)

    md_report = generate_diff_report(
        report_a_path=str(args.report_a),
        report_b_path=str(args.report_b),
        data_a=data_a,
        data_b=data_b,
        output_dir=args.output_dir,
    )
    print("\n" + md_report)


if __name__ == "__main__":
    main()
