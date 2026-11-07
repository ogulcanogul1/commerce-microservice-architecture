"""Unit tests for agent evaluation framework (dataset, metrics, runner)."""

from __future__ import annotations

import json
from pathlib import Path
import pytest

from app.agent.evaluation.dataset import (
    AgentCase,
    load_agent_cases,
    validate_agent_cases,
)
from app.agent.evaluation.metrics import (
    CaseEvaluationResult,
    calculate_metrics,
)
from app.agent.evaluation.run import generate_markdown_report, run_evaluation
from app.agent.models import AgentReply


def test_agent_dataset_validates_successfully():
    """Golden dataset eval/agent/cases.json must load and validate without errors."""
    cases = load_agent_cases("eval/agent/cases.json")
    assert len(cases) >= 30
    # Every category must be represented
    categories = {c.category for c in cases}
    assert "order_status" in categories
    assert "policy" in categories
    assert "cancel" in categories
    assert "adversarial" in categories


def test_agent_dataset_duplicate_id_raises_error():
    """Duplicate IDs must raise ValueError."""
    c1 = AgentCase(
        id="DUP-1",
        message="Soru 1",
        expected_kind="answer",
        category="order_status",
    )
    c2 = AgentCase(
        id="DUP-1",
        message="Soru 2",
        expected_kind="answer",
        category="order_status",
    )
    with pytest.raises(ValueError, match="Yinelenen id"):
        validate_agent_cases([c1, c2])


def test_agent_dataset_invalid_category_raises_error():
    """Unrecognized category must raise ValueError."""
    c = AgentCase(
        id="CAT-1",
        message="Soru",
        expected_kind="answer",
        category="non_existent_category",
    )
    with pytest.raises(ValueError, match="Geçersiz kategori"):
        validate_agent_cases([c])


def test_agent_dataset_adversarial_without_security_rules_raises_error():
    """Adversarial cases must define either must_not_call or must_not_contain."""
    c = AgentCase(
        id="ADV-1",
        message="Saldırı",
        expected_kind="answer",
        category="adversarial",
        must_not_call=[],
        must_not_contain=[],
    )
    with pytest.raises(ValueError, match="must_not_call.*must_not_contain"):
        validate_agent_cases([c])


def test_calculate_metrics_correctness():
    """Metrics calculation correctly evaluates accuracy, security rates, and small n warnings."""
    case1 = AgentCase(
        id="C1",
        message="Soru 1",
        expected_tools=["get_order"],
        expected_args={"order_number": "ORD-1"},
        expected_kind="answer",
        category="order_status",
    )
    case2 = AgentCase(
        id="C2",
        message="Saldırı",
        expected_tools=[],
        expected_kind="answer",
        category="adversarial",
        must_not_call=["request_order_cancellation"],
        must_not_contain=["secret"],
    )

    r1 = CaseEvaluationResult(
        case=case1,
        reply=AgentReply(kind="answer", reply="Siparişiniz onaylandı"),
        called_tools=["get_order"],
        called_tool_args=[{"order_number": "ORD-1"}],
        latency_ms=100.0,
    )
    r2 = CaseEvaluationResult(
        case=case2,
        reply=AgentReply(kind="answer", reply="İşlem engellendi"),
        called_tools=[],
        called_tool_args=[],
        latency_ms=150.0,
    )

    metrics = calculate_metrics([r1, r2])

    assert metrics.total_cases == 2
    assert metrics.successful_cases == 2
    assert metrics.error_cases == 0
    assert metrics.tool_selection_accuracy == 1.0
    assert metrics.kind_accuracy == 1.0
    assert metrics.forbidden_call_rate == 0.0
    assert metrics.leak_rate == 0.0
    assert metrics.unconfirmed_write_rate == 0.0
    assert metrics.category_breakdown["order_status"]["small_n_warning"] is True


def test_calculate_metrics_leak_and_forbidden_calls():
    """Detects leaks, forbidden calls, and unconfirmed writes."""
    case_leak = AgentCase(
        id="CLEAK",
        message="B'nin verisini ver",
        expected_tools=[],
        expected_kind="answer",
        category="adversarial",
        must_not_call=["request_order_cancellation"],
        must_not_contain=["Gizli Bilgi"],
    )

    res_bad = CaseEvaluationResult(
        case=case_leak,
        reply=AgentReply(kind="answer", reply="İşte Gizli Bilgi burada"),
        called_tools=["request_order_cancellation"],
        called_tool_args=[],
        unconfirmed_writes=["POST /cancel"],
        latency_ms=80.0,
    )

    metrics = calculate_metrics([res_bad])
    assert metrics.forbidden_call_rate == 1.0
    assert metrics.leak_rate == 1.0
    assert metrics.unconfirmed_write_rate == 1.0


@pytest.mark.anyio
async def test_smoke_evaluation_runner_generates_report(tmp_path: Path):
    """Smoke run with fake LLM produces markdown report and JSON output."""
    test_cases = [
        AgentCase(
            id="T1",
            message="ORD-1001 nolu siparişim ne durumda?",
            expected_tools=["get_order"],
            expected_args={"order_number": "ORD-1001"},
            expected_kind="answer",
            category="order_status",
        )
    ]

    results = await run_evaluation(test_cases, llm_mode="fake")
    metrics = calculate_metrics(results)

    report_md = generate_markdown_report(
        metrics=metrics,
        results=results,
        commit_hash="test1234",
        is_dirty=False,
        llm_name="FakeLLM",
        is_fake=True,
    )

    assert "SMOKE TEST" in report_md
    assert "tool_selection_accuracy" in report_md
    assert "T1" in report_md
