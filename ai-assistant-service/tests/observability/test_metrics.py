"""Prometheus Metrikleri ve HttpMetricsMiddleware Birim Testleri.

Bu test modülü:
1. HttpMetricsMiddleware'in istek sürelerini ölçüp HTTP_SERVER_REQUESTS histogramına eklediğini,
2. Dinamik path parametrelerinin şablona dönüştürüldüğünü (kardinalite patlaması koruması),
3. Eşleşmeyen 404 rotalarının 'UNMATCHED' olarak etiketlendiğini,
4. ToolRegistry'nin tool sürelerini ve bilinmeyen tool'ları 'unknown' olarak AI_TOOL_CALL_DURATION'a yazdığını,
5. AgentService'in LLM çağrı süresini (AI_LLM_REQUEST_DURATION) ve token sayaçlarını (AI_LLM_TOKENS) artırdığını doğrular.
"""

from unittest.mock import AsyncMock
from fastapi import FastAPI
import pytest
from prometheus_client import REGISTRY
from starlette.testclient import TestClient

from app.agent.models import AgentReply
from app.agent.service import AgentService
from app.agent.tools.base import Tool, ToolContext, ToolResult
from app.agent.tools.registry import ToolRegistry
from app.core.security import RequestContext
from app.llm.base import BaseLLMProvider, LLMResponse, TokenUsage
from app.observability.metrics import (
    AI_LLM_REQUEST_DURATION,
    AI_LLM_TOKENS,
    AI_TOOL_CALL_DURATION,
    HTTP_SERVER_REQUESTS,
    HttpMetricsMiddleware,
)


def _get_metric_val(name: str, labels: dict[str, str]) -> float:
    """Prometheus Default Registry'den belirtilen etiketlere sahip metriğin o anki değerini döner."""
    val = REGISTRY.get_sample_value(name, labels)
    return val if val is not None else 0.0


def test_http_metrics_middleware_route_template_cardinality():
    """HttpMetricsMiddleware'in dinamik path parametrelerini route şablonuyla etiketlediğini

    ve ham URL'ler için sınırsız time-series açılmadığını doğrular.
    """
    app = FastAPI()
    app.add_middleware(HttpMetricsMiddleware)

    @app.get("/items/{item_id}")
    async def get_item(item_id: str):
        return {"item": item_id}

    client = TestClient(app)

    labels = {
        "method": "GET",
        "uri": "/items/{item_id}",
        "status": "200",
        "outcome": "SUCCESS",
    }
    before_count = _get_metric_val("http_server_requests_seconds_count", labels)

    # İki farklı ID ile istek at
    resp1 = client.get("/items/12345")
    assert resp1.status_code == 200

    resp2 = client.get("/items/67890")
    assert resp2.status_code == 200

    after_count = _get_metric_val("http_server_requests_seconds_count", labels)
    # Şablon serisi 2 artmış olmalı
    assert after_count - before_count == 2.0

    # Ham URL'lerin label olmadığını doğrula
    raw_labels = {"method": "GET", "uri": "/items/12345", "status": "200", "outcome": "SUCCESS"}
    assert _get_metric_val("http_server_requests_seconds_count", raw_labels) == 0.0


def test_http_metrics_middleware_unmatched_route_404():
    """Tanımsız bir URL çağrıldığında (404) uri etiketinin 'UNMATCHED' olduğunu doğrular."""
    app = FastAPI()
    app.add_middleware(HttpMetricsMiddleware)
    client = TestClient(app)

    labels = {
        "method": "GET",
        "uri": "UNMATCHED",
        "status": "404",
        "outcome": "CLIENT_ERROR",
    }
    before_count = _get_metric_val("http_server_requests_seconds_count", labels)

    client.get("/non-existent-endpoint-abc")

    after_count = _get_metric_val("http_server_requests_seconds_count", labels)
    assert after_count - before_count == 1.0


@pytest.mark.anyio
async def test_tool_registry_metrics_known_and_unknown_tools():
    """ToolRegistry.execute çağrılarında kayıtlı aracın kendi adıyla, bilinmeyen

    araçların ise 'unknown' adıyla metriğe kaydedildiğini doğrular.
    """
    registry = ToolRegistry()

    from pydantic import BaseModel

    class DummyArgs(BaseModel):
        pass

    # Sahte bir tool kaydet
    class DummyTool(Tool):
        name = "dummy_tool"
        description = "Test tool"
        args_model = DummyArgs

        async def run(self, args: BaseModel, ctx: ToolContext) -> ToolResult:
            return ToolResult(ok=True, data={"result": "ok"})

    registry.register(DummyTool())

    ctx = ToolContext(user_id="user-1", correlation_id="c-1", question="test question")

    # 1. Kayıtlı tool çalıştır
    known_labels = {"tool_name": "dummy_tool", "outcome": "ok"}
    before_known = _get_metric_val("ai_tool_call_duration_seconds_count", known_labels)

    await registry.execute("dummy_tool", {}, ctx)

    after_known = _get_metric_val("ai_tool_call_duration_seconds_count", known_labels)
    assert after_known - before_known == 1.0

    # 2. Bilinmeyen (modelin uydurduğu) tool çalıştır
    unknown_labels = {"tool_name": "unknown", "outcome": "invalid_args"}
    before_unknown = _get_metric_val("ai_tool_call_duration_seconds_count", unknown_labels)

    await registry.execute("hallucinated_tool_xyz", {}, ctx)

    after_unknown = _get_metric_val("ai_tool_call_duration_seconds_count", unknown_labels)
    assert after_unknown - before_unknown == 1.0

    # Uydurulan isimle yeni bir Prometheus time-series AÇILMAMALI
    bad_labels = {"tool_name": "hallucinated_tool_xyz", "outcome": "invalid_args"}
    assert _get_metric_val("ai_tool_call_duration_seconds_count", bad_labels) == 0.0


@pytest.mark.anyio
async def test_agent_service_llm_duration_and_token_counters():
    """AgentService.chat içinde LLM süre histogramının ve token sayaçlarının arttığını doğrular."""
    mock_llm = AsyncMock(spec=BaseLLMProvider)
    mock_llm.provider = "test_llm_provider"
    # LLM yanıtı ve token kullanımı ayarla
    mock_llm.generate.return_value = LLMResponse(
        content="Merhaba! Size nasıl yardımcı olabilirim?",
        tool_calls=[],
        usage=TokenUsage(input_tokens=42, output_tokens=18),
        provider="test_llm_provider",
        model="test-model",
    )

    registry = ToolRegistry()
    service = AgentService(llm=mock_llm, registry=registry)

    req_ctx = RequestContext(user_id="user-tok-1", correlation_id="c-tok-1")

    # Metrik sayaçlarının önceki değerleri
    dur_labels = {"provider": "test_llm_provider", "outcome": "success"}
    in_labels = {"provider": "test_llm_provider", "direction": "input"}
    out_labels = {"provider": "test_llm_provider", "direction": "output"}

    before_dur = _get_metric_val("ai_llm_request_duration_seconds_count", dur_labels)
    before_in_tokens = _get_metric_val("ai_llm_tokens_total", in_labels)
    before_out_tokens = _get_metric_val("ai_llm_tokens_total", out_labels)

    reply = await service.chat("Merhaba", req_ctx)
    assert reply.kind == "answer"

    # Sonraki değerleri doğrula
    after_dur = _get_metric_val("ai_llm_request_duration_seconds_count", dur_labels)
    after_in_tokens = _get_metric_val("ai_llm_tokens_total", in_labels)
    after_out_tokens = _get_metric_val("ai_llm_tokens_total", out_labels)

    assert after_dur - before_dur == 1.0
    assert after_in_tokens - before_in_tokens == 42.0
    assert after_out_tokens - before_out_tokens == 18.0
