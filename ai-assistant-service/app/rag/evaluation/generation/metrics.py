"""Deterministic evaluation metrics for RAG generation quality.

Bu modül, üretilen RAG cevaplarını (RagAnswer) altın cevap setiyle (AnswerCase)
karşılaştırarak doğruluk (accuracy), halüsinasyon oranı (hallucination_rate),
yanlış abstain oranı (false_abstain_rate) ve atıf geçerlilik oranı gibi
deterministik kalite metriklerini hesaplar.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from app.rag.evaluation.chunking.dataset import normalize_for_match
from app.rag.evaluation.generation.dataset import AnswerCase
from app.rag.generation.models import AbstainReason, RagAnswer

if TYPE_CHECKING:
    pass


class CaseResult(BaseModel):
    """Detailed score and telemetry result for an individual evaluated case."""

    case_id: str = Field(description="Case identifier (e.g. G01, U01)")
    category: str = Field(description="Evaluation category")
    question: str = Field(description="Evaluated question text")
    answerable: bool = Field(description="Whether the case is answerable according to corpus")
    status: str = Field(description="Generation result status ('answered' or 'abstained')")
    abstain_reason: AbstainReason | None = Field(default=None, description="Reason if abstained")
    fact_recall: float = Field(description="Fraction of expected facts found in answer (0.0 to 1.0)")
    forbidden_hit: bool = Field(description="True if any forbidden hallucination was generated")
    correct: bool = Field(description="Overall boolean success (answered with full recall for answerable, or abstained for unanswerable)")
    attempts: int = Field(default=1, description="Number of LLM attempts taken")
    citations_valid: bool = Field(default=True, description="True if no citation or grounding issues remain")
    latency_ms: float = Field(default=0.0, description="End-to-end service response latency in milliseconds")
    input_tokens: int = Field(default=0, description="Total input tokens consumed")
    output_tokens: int = Field(default=0, description="Total output tokens generated")
    answer_text: str = Field(default="", description="Generated response string")
    expected_facts: list[str] = Field(default_factory=list, description="Expected key facts")
    notes: str | None = Field(default=None, description="Case notes")
    error: str | None = Field(default=None, description="Exception message if execution crashed")
    rerank_status: str | None = Field(default=None, description="Rerank execution status ('ok', 'failed', 'disabled')")


class CategoryEvalSummary(BaseModel):
    """Aggregated evaluation metrics for a single question category."""

    name: str = Field(description="Category name")
    total: int = Field(description="Total number of evaluated cases in category")
    correct: int = Field(description="Number of correct cases")
    accuracy: float = Field(description="Ratio of correct cases")
    small_n_warning: str | None = Field(default=None, description="Warning message if sample size n < 10")


class GenerationEvalSummary(BaseModel):
    """Comprehensive generation evaluation summary report across all cases."""

    total_cases: int = Field(description="Total cases evaluated")
    answerable_count: int = Field(description="Number of answerable cases")
    unanswerable_count: int = Field(description="Number of unanswerable cases")
    errors_count: int = Field(default=0, description="Number of cases with unexpected execution crashes")
    answer_accuracy: float = Field(description="Accuracy on answerable cases (correct / answerable_count)")
    hallucination_rate: float = Field(description="Hallucination rate on unanswerable cases (answered / unanswerable_count)")
    false_abstain_rate: float = Field(description="False abstain rate on answerable cases (abstained / answerable_count)")
    false_abstain_by_reason: dict[str, int] = Field(default_factory=dict, description="Breakdown of false abstain reasons")
    citation_valid_rate: float = Field(description="Ratio of answered queries where citations are completely valid")
    retry_rate: float = Field(description="Ratio of cases requiring attempt 2")
    avg_input_tokens: float = Field(default=0.0, description="Average prompt input tokens")
    avg_output_tokens: float = Field(default=0.0, description="Average generated output tokens")
    latency_p50_ms: float = Field(default=0.0, description="Median latency in milliseconds")
    latency_p95_ms: float = Field(default=0.0, description="95th percentile latency in milliseconds")
    categories: dict[str, CategoryEvalSummary] = Field(default_factory=dict, description="Metrics grouped by category")


def score_case(
    case: AnswerCase,
    answer: RagAnswer | None = None,
    latency_ms: float = 0.0,
    error: str | None = None,
) -> CaseResult:
    """Score a single generated RAG answer against golden case ground truth.

    Deterministik Değerlendirme Kuralları:
    0. Hata Kontrolü: error doluysa sistem hatası oluşmuştur (timeout, kesinti vb.).
       Hatalar metriklerden ayrı tutulur ve kesinlikle doğru sayılamaz (correct=False, status='error').
    1. fact_recall: expected_facts içindeki her olgunun normalize edilmiş hali cevapta aranır.
       Tümü bulunursa 1.0, hiçbiri bulunamazsa 0.0.
    2. forbidden_hit: forbidden_facts içindeki herhangi bir yanlış/uydurma olgu cevapta
       geçiyorsa True olur.
    3. correct:
       - Cevaplanabilir soru (answerable=True): status='answered' VE fact_recall == 1.0 VE forbidden_hit == False.
       - Cevaplanamaz soru (answerable=False): status='abstained'.
    4. citations_valid: answered durumunda validation_issues boşsa True.
    """
    if error is not None or answer is None:
        return CaseResult(
            case_id=case.id,
            category=case.category,
            question=case.question,
            answerable=case.answerable,
            status="error",
            abstain_reason=None,
            fact_recall=0.0,
            forbidden_hit=False,
            correct=False,
            attempts=1,
            citations_valid=False,
            latency_ms=latency_ms,
            input_tokens=0,
            output_tokens=0,
            answer_text="",
            expected_facts=case.expected_facts,
            notes=case.notes,
            error=error or "Unknown error",
        )

    normalized_answer = normalize_for_match(answer.answer)

    # 1. Beklenen olguların taranması (fact_recall)
    if not case.expected_facts:
        fact_recall = 1.0
    else:
        matched_count = 0
        for fact in case.expected_facts:
            norm_fact = normalize_for_match(fact)
            if norm_fact in normalized_answer:
                matched_count += 1
        fact_recall = matched_count / len(case.expected_facts)

    # 2. Yasaklı/uydurma olguların taranması (forbidden_hit)
    forbidden_hit = False
    for forbidden in case.forbidden_facts:
        norm_forbidden = normalize_for_match(forbidden)
        if norm_forbidden and norm_forbidden in normalized_answer:
            forbidden_hit = True
            break

    # 3. Genel doğruluk kararı (correct)
    if case.answerable:
        # Cevaplanabilir soruda hem answered olmalı, hem tüm beklenen olgular geçmeli, hem de yasaklı ifade olmamalıdır
        correct = (
            answer.status == "answered"
            and math.isclose(fact_recall, 1.0, abs_tol=1e-5)
            and not forbidden_hit
        )
    else:
        # Cevaplanamaz soruda tek başarı kriteri modelin sessiz kalmasıdır (abstained)
        correct = answer.status == "abstained"

    # 4. Atıf geçerliliği kontrolü
    if answer.status == "answered":
        citations_valid = len(answer.validation_issues) == 0
    else:
        citations_valid = True

    # Token kullanımı hesaplama
    input_tokens = (answer.usage.input_tokens or 0) if answer.usage else 0
    output_tokens = (answer.usage.output_tokens or 0) if answer.usage else 0

    return CaseResult(
        case_id=case.id,
        category=case.category,
        question=case.question,
        answerable=case.answerable,
        status=answer.status,
        abstain_reason=answer.abstain_reason,
        fact_recall=fact_recall,
        forbidden_hit=forbidden_hit,
        correct=correct,
        attempts=answer.attempts,
        citations_valid=citations_valid,
        latency_ms=latency_ms,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        answer_text=answer.answer,
        expected_facts=case.expected_facts,
        notes=case.notes,
        error=error,
        rerank_status=getattr(answer, "rerank_status", None) if answer else None,
    )


def compute_generation_summary(
    results: list[CaseResult],
) -> GenerationEvalSummary:
    """Aggregate individual case results into a comprehensive generation eval summary."""
    if not results:
        return GenerationEvalSummary(
            total_cases=0,
            answerable_count=0,
            unanswerable_count=0,
            answer_accuracy=0.0,
            hallucination_rate=0.0,
            false_abstain_rate=0.0,
            citation_valid_rate=0.0,
            retry_rate=0.0,
        )

    total_cases = len(results)
    errors_count = sum(1 for r in results if r.error is not None)

    # Hatalar metriklerden ayrı sayılır (Plan Karar 11 ve Adım 8.3)
    valid_answerable = [r for r in results if r.answerable and r.error is None]
    valid_unanswerable = [r for r in results if not r.answerable and r.error is None]

    # 1. Cevaplanabilir Metrikleri
    ans_count = len(valid_answerable)
    if ans_count > 0:
        ans_correct = sum(1 for r in valid_answerable if r.correct)
        answer_accuracy = ans_correct / ans_count
        false_abstained = [r for r in valid_answerable if r.status == "abstained"]
        false_abstain_rate = len(false_abstained) / ans_count

        false_abstain_by_reason: dict[str, int] = {}
        for r in false_abstained:
            reason_str = str(r.abstain_reason) if r.abstain_reason else "unknown"
            false_abstain_by_reason[reason_str] = false_abstain_by_reason.get(reason_str, 0) + 1
    else:
        answer_accuracy = 0.0
        false_abstain_rate = 0.0
        false_abstain_by_reason = {}

    # 2. Cevaplanamaz Metrikleri (Halüsinasyon)
    unans_count = len(valid_unanswerable)
    if unans_count > 0:
        # Cevaplanamaz soruya cevap verilmesi en pahalı hatadır (halüsinasyon)
        hallucinated_count = sum(1 for r in valid_unanswerable if r.status == "answered")
        hallucination_rate = hallucinated_count / unans_count
    else:
        hallucination_rate = 0.0

    # 3. Atıf ve Retry Oranları
    answered_all = [r for r in results if r.status == "answered"]
    if answered_all:
        citation_valid_rate = sum(1 for r in answered_all if r.citations_valid) / len(answered_all)
    else:
        citation_valid_rate = 1.0

    retry_count = sum(1 for r in results if r.attempts > 1)
    retry_rate = retry_count / total_cases

    # 4. Token ve Gecikme Ortalamaları
    valid_token_results = [r for r in results if r.input_tokens > 0 or r.output_tokens > 0]
    if valid_token_results:
        avg_input_tokens = sum(r.input_tokens for r in valid_token_results) / len(valid_token_results)
        avg_output_tokens = sum(r.output_tokens for r in valid_token_results) / len(valid_token_results)
    else:
        avg_input_tokens = 0.0
        avg_output_tokens = 0.0

    # Gecikme persentilleri (p50 ve p95)
    latencies = sorted(r.latency_ms for r in results if r.latency_ms > 0)
    if latencies:
        p50_idx = int(0.50 * (len(latencies) - 1))
        p95_idx = int(0.95 * (len(latencies) - 1))
        latency_p50_ms = latencies[p50_idx]
        latency_p95_ms = latencies[p95_idx]
    else:
        latency_p50_ms = 0.0
        latency_p95_ms = 0.0

    # 5. Kategori Kırılımı
    categories: dict[str, CategoryEvalSummary] = {}
    cases_by_cat: dict[str, list[CaseResult]] = {}
    for r in results:
        cases_by_cat.setdefault(r.category, []).append(r)

    for cat_name, cat_results in cases_by_cat.items():
        valid_cat_results = [r for r in cat_results if r.error is None]
        cat_total = len(valid_cat_results)
        cat_correct = sum(1 for r in valid_cat_results if r.correct)
        cat_acc = cat_correct / cat_total if cat_total > 0 else 0.0
        warning = f"n={cat_total}, yorumlama" if cat_total < 10 else None
        categories[cat_name] = CategoryEvalSummary(
            name=cat_name,
            total=cat_total,
            correct=cat_correct,
            accuracy=cat_acc,
            small_n_warning=warning,
        )

    return GenerationEvalSummary(
        total_cases=total_cases,
        answerable_count=ans_count,
        unanswerable_count=unans_count,
        errors_count=errors_count,
        answer_accuracy=answer_accuracy,
        hallucination_rate=hallucination_rate,
        false_abstain_rate=false_abstain_rate,
        false_abstain_by_reason=false_abstain_by_reason,
        citation_valid_rate=citation_valid_rate,
        retry_rate=retry_rate,
        avg_input_tokens=avg_input_tokens,
        avg_output_tokens=avg_output_tokens,
        latency_p50_ms=latency_p50_ms,
        latency_p95_ms=latency_p95_ms,
        categories=categories,
    )
