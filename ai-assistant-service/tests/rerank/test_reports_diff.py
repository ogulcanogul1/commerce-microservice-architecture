from pathlib import Path
from app.rag.evaluation.rerank.reports_diff import (
    analyze_generation_flips,
    check_fairness,
    generate_diff_report,
)


def test_check_fairness_equal():
    meta_a = {
        "embedder": "openai/text-embedding-3-small",
        "llm_provider": "gemini",
        "llm_model": "gemini-2.0-flash",
        "min_dense_score": 0.5,
        "top_k": 5,
        "token_budget": 1500,
        "git_commit": "abc1234",
    }
    meta_b = dict(meta_a)

    warnings = check_fairness(meta_a, meta_b, count_a=42, count_b=42)
    assert warnings == []


def test_check_fairness_differences():
    meta_a = {
        "embedder": "openai/text-embedding-3-small",
        "llm_provider": "gemini",
        "git_commit": "abc1234",
    }
    meta_b = {
        "embedder": "fake/bow",  # Farklı embedder!
        "llm_provider": "openai",  # Farklı LLM!
        "git_commit": "def5678",
    }

    warnings = check_fairness(meta_a, meta_b, count_a=42, count_b=30)
    assert len(warnings) >= 3
    warn_text = " ".join(warnings)
    assert "Embedder" in warn_text
    assert "LLM Sağlayıcısı" in warn_text
    assert "Toplam soru sayısı farklı" in warn_text
    assert "Git commit farklı" in warn_text


def test_analyze_generation_flips():
    results_a = [
        {"case_id": "C1", "answerable": True, "status": "abstained", "correct": False, "question": "Soru 1"},
        {"case_id": "C2", "answerable": True, "status": "answered", "correct": True, "question": "Soru 2"},
        {"case_id": "C3", "answerable": True, "status": "answered", "correct": True, "question": "Soru 3"},
        {"case_id": "U1", "answerable": False, "status": "abstained", "correct": True, "question": "Cevaplanamaz Soru"},
    ]
    results_b = [
        {"case_id": "C1", "answerable": True, "status": "answered", "correct": True, "question": "Soru 1"},  # Düzelen!
        {"case_id": "C2", "answerable": True, "status": "abstained", "correct": False, "question": "Soru 2"},  # Bozulan!
        {"case_id": "C3", "answerable": True, "status": "answered", "correct": True, "question": "Soru 3"},  # Değişmeyen
        {"case_id": "U1", "answerable": False, "status": "answered", "correct": False, "answer_text": "Uydurma", "question": "Cevaplanamaz Soru"},  # Halüsinasyon!
    ]

    flips = analyze_generation_flips(results_a, results_b)

    assert len(flips["improved"]) == 1
    assert flips["improved"][0]["id"] == "C1"

    assert len(flips["regressed"]) == 2
    regressed_ids = [r["id"] for r in flips["regressed"]]
    assert "C2" in regressed_ids
    assert "U1" in regressed_ids

    assert flips["unchanged_count"] == 1  # C3 (her ikisinde de correct=True)

    # Yeni halüsinasyon kontrolü
    assert len(flips["new_hallucinations"]) == 1
    assert flips["new_hallucinations"][0]["id"] == "U1"


def test_generate_diff_report(tmp_path: Path):
    data_a = {
        "meta": {"embedder": "fake", "git_commit": "aaa", "rerank": "off"},
        "summary": {"answer_accuracy": 0.8, "hallucination_rate": 0.0, "latency_p50_ms": 100.0},
        "results": [
            {"case_id": "Q1", "answerable": True, "status": "answered", "correct": True, "question": "Soru 1"}
        ],
    }
    data_b = {
        "meta": {"embedder": "fake", "git_commit": "aaa", "rerank": "on", "reranker_id": "fake"},
        "summary": {"answer_accuracy": 0.9, "hallucination_rate": 0.0, "latency_p50_ms": 110.0},
        "results": [
            {"case_id": "Q1", "answerable": True, "status": "answered", "correct": True, "question": "Soru 1"}
        ],
    }

    report_md = generate_diff_report("a.json", "b.json", data_a, data_b, output_dir=tmp_path)

    assert "RAG Generation Karşılaştırma Raporu" in report_md
    assert "Cevap Doğruluğu" in report_md
    assert "+10.00%" in report_md
    assert "GÜRÜLTÜ UYARISI" in report_md  # 0 <= 2 flips olduğu için

    saved_files = list(tmp_path.glob("diff-*.md"))
    assert len(saved_files) == 1
