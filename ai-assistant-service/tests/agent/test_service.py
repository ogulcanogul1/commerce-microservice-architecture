import asyncio
import logging
from unittest.mock import AsyncMock, MagicMock
import pytest

from app.agent.pending import InMemoryPendingActionStore
from app.agent.service import AgentService
from app.agent.tools.actions import RequestOrderCancellationTool
from app.agent.tools.base import ToolContext, ToolResult
from app.agent.tools.orders import GetOrderTool
from app.agent.tools.policy import SearchPolicyTool
from app.agent.tools.registry import ToolRegistry
from app.api.answer import AnswerResponse, CitationResponse
from app.clients.models import OrderItemView, OrderView
from app.core.security import RequestContext
from app.llm.base import ToolCallRequest
from app.llm.fake import FakeLLMProvider
from decimal import Decimal
from datetime import datetime, timezone


def _sample_order(order_number: str = "ORD-100", customer_id: str = "user-123") -> OrderView:
    return OrderView(
        id="ord-uuid-1",
        orderNumber=order_number,
        customerId=customer_id,
        status="CONFIRMED",
        totalAmount=Decimal("1500"),
        currency="TRY",
        items=[OrderItemView(productName="Gömlek", sku="SKU-1", quantity=1)],
        createdAt=datetime.now(timezone.utc),
        updatedAt=datetime.now(timezone.utc),
    )


@pytest.fixture
def base_context() -> RequestContext:
    return RequestContext(
        user_id="user-123",
        correlation_id="corr-xyz",
    )


@pytest.mark.anyio
async def test_service_happy_path_get_order(base_context: RequestContext) -> None:
    mock_order_client = AsyncMock()
    mock_order_client.get_order_by_number.return_value = _sample_order()

    registry = ToolRegistry()
    registry.register(GetOrderTool(order_client=mock_order_client))

    # FakeLLM: 1. adımda tool çağrısı ister, 2. adımda nihai yanıtı üretir
    fake_llm = FakeLLMProvider(
        responses=[
            [
                ToolCallRequest(
                    call_id="call-1",
                    tool_name="get_order",
                    arguments={"order_number": "ORD-100"},
                )
            ],
            "Siparişiniz ORD-100 onaylandı ve tutarı 1500 TL.",
        ]
    )

    service = AgentService(llm=fake_llm, registry=registry)
    reply = await service.chat("ORD-100 nolu siparişim ne durumda?", base_context)

    assert reply.kind == "answer"
    assert reply.steps == 2
    assert "ORD-100" in reply.reply
    assert reply.usage is not None
    assert reply.usage.input_tokens > 0


@pytest.mark.anyio
async def test_service_policy_tool_terminal_execution(base_context: RequestContext) -> None:
    mock_rag = AsyncMock()
    mock_rag.answer.return_value = AnswerResponse(
        status="answered",
        answer="İade süresi 14 gündür [1].",
        citations=[
            CitationResponse(
                number=1,
                chunk_id="chk-1",
                source_file="iade.pdf",
                page_start=1,
                page_end=1,
            )
        ],
    )

    registry = ToolRegistry()
    registry.register(SearchPolicyTool(rag_service=mock_rag))

    # FakeLLM search_policy talep eder
    fake_llm = FakeLLMProvider(
        responses=[
            [
                ToolCallRequest(
                    call_id="call-p",
                    tool_name="search_policy",
                    arguments={},
                )
            ],
            "Bu metin ASLA üretilmemeli çünkü RAG terminaldir",
        ]
    )

    service = AgentService(llm=fake_llm, registry=registry)
    reply = await service.chat("İade süresi ne kadar?", base_context)

    assert reply.kind == "policy_answer"
    # RAG cevabı modele özetletilmeden BİREBİR dönmeli
    assert reply.reply == "İade süresi 14 gündür [1]."
    assert len(reply.citations) == 1
    # LLM yalnızca 1 kez çağrıldı (ikinci çağrı yapılmadı)
    assert len(fake_llm.calls) == 1


@pytest.mark.anyio
async def test_service_search_policy_and_get_order_in_same_step(base_context: RequestContext) -> None:
    mock_rag = AsyncMock()
    mock_rag.answer.return_value = AnswerResponse(
        status="abstained",
        answer="Dokümanlarda bulunamadı.",
        abstain_reason="no_results",
        citations=[],
    )
    mock_order = AsyncMock()

    registry = ToolRegistry()
    registry.register(SearchPolicyTool(rag_service=mock_rag))
    registry.register(GetOrderTool(order_client=mock_order))

    # LLM aynı anda hem search_policy hem get_order çağırdı (kural ihlali)
    fake_llm = FakeLLMProvider(
        responses=[
            [
                ToolCallRequest(call_id="c1", tool_name="search_policy", arguments={}),
                ToolCallRequest(call_id="c2", tool_name="get_order", arguments={"order_number": "ORD-1"}),
            ]
        ]
    )

    service = AgentService(llm=fake_llm, registry=registry)
    reply = await service.chat("Karma soru", base_context)

    # Karar 4 gereği yalnızca search_policy çalışmalı
    assert reply.kind == "abstained"
    mock_order.get_order_by_number.assert_not_called()


@pytest.mark.anyio
async def test_service_grounding_violation_triggers_retry(base_context: RequestContext) -> None:
    mock_order_client = AsyncMock()
    mock_order_client.get_order_by_number.return_value = _sample_order()

    registry = ToolRegistry()
    registry.register(GetOrderTool(order_client=mock_order_client))

    # FakeLLM:
    # Adım 1: get_order çağırır
    # Adım 2: Halüsinasyon yapar ("7 gün" der; 7 araç sonuçlarında yok!)
    # Adım 3: Düzeltme uyarısı alır ve sayıyı silip düzeltir
    fake_llm = FakeLLMProvider(
        responses=[
            [
                ToolCallRequest(
                    call_id="call-1",
                    tool_name="get_order",
                    arguments={"order_number": "ORD-100"},
                )
            ],
            "Siparişiniz onaylandı, 7 gün sonra teslim edilecek.",
            "Siparişiniz onaylandı ve tutarı 1500 TL.",
        ]
    )

    service = AgentService(llm=fake_llm, registry=registry)
    reply = await service.chat("Siparişim ne durumda?", base_context)

    assert reply.kind == "answer"
    assert "1500 TL" in reply.reply
    assert "7 gün" not in reply.reply
    assert reply.steps == 3


@pytest.mark.anyio
async def test_service_grounding_failure_falls_back(base_context: RequestContext) -> None:
    mock_order_client = AsyncMock()
    mock_order_client.get_order_by_number.return_value = _sample_order()

    registry = ToolRegistry()
    registry.register(GetOrderTool(order_client=mock_order_client))

    # FakeLLM uyarıya rağmen sayı uydurmaya devam eder
    fake_llm = FakeLLMProvider(
        responses=[
            [
                ToolCallRequest(
                    call_id="call-1",
                    tool_name="get_order",
                    arguments={"order_number": "ORD-100"},
                )
            ],
            "Siparişiniz 7 gün sonra teslim edilecek.",
            "Yine 7 gün diyorum.",
        ]
    )

    service = AgentService(llm=fake_llm, registry=registry)
    reply = await service.chat("Siparişim ne durumda?", base_context)

    # İkinci denemede de geçmediği için fallback'e düşmeli
    assert reply.kind == "fallback"
    assert "müşteri temsilcisine" in reply.reply


@pytest.mark.anyio
async def test_service_pending_action_returns_summary(base_context: RequestContext) -> None:
    mock_order_client = AsyncMock()
    mock_order_client.get_order_by_number.return_value = _sample_order()
    store = InMemoryPendingActionStore()

    registry = ToolRegistry()
    registry.register(RequestOrderCancellationTool(order_client=mock_order_client, action_store=store))

    fake_llm = FakeLLMProvider(
        responses=[
            [
                ToolCallRequest(
                    call_id="call-c",
                    tool_name="request_order_cancellation",
                    arguments={"order_number": "ORD-100", "reason": "Fiyatı pahalı geldi"},
                )
            ],
            "İptal isteğinizi aldım.",
        ]
    )

    service = AgentService(llm=fake_llm, registry=registry)
    reply = await service.chat("Siparişimi iptal et", base_context)

    assert reply.kind == "pending_action"
    assert reply.pending_action is not None
    assert reply.pending_action.action_type == "cancel_order"
    # Karar 3 & 6: reply alanı action.summary ile eşleşmeli
    assert reply.reply == reply.pending_action.summary
    assert "ORD-100" in reply.reply


@pytest.mark.anyio
async def test_service_pii_masked_in_messages_to_llm(base_context: RequestContext) -> None:
    fake_llm = FakeLLMProvider(responses=["Yardımcı olabilirim."])
    registry = ToolRegistry()

    service = AgentService(llm=fake_llm, registry=registry)
    # TCKN içeren soru
    await service.chat("TCKN: 54321098710 siparişimi kontrol eder misiniz?", base_context)

    # Modele giden mesajda ham TCKN ASLA olmamalı, [TCKN] olmalı
    sent_msgs = fake_llm.calls[0]["messages"]
    user_msg = next(m for m in sent_msgs if m.role == "user")
    assert "54321098710" not in user_msg.content
    assert "[TCKN]" in user_msg.content


@pytest.mark.anyio
async def test_service_step_limit_exceeded_falls_back(base_context: RequestContext) -> None:
    # 4 adım boyunca sürekli tool çağıran sonsuz döngü simülasyonu
    tool_req = [
        ToolCallRequest(
            call_id=f"c-{i}",
            tool_name="dummy",
            arguments={},
        )
        for i in range(1)
    ]
    fake_llm = FakeLLMProvider(responses=[tool_req, tool_req, tool_req, tool_req])

    class DummyTool:
        name = "dummy"
        description = "d"
        class args_model:
            @classmethod
            def model_validate(cls, d): return d
        def definition(self):
            from app.llm.base import ToolDefinition
            return ToolDefinition(name="dummy", description="d", parameters={})
        async def run(self, args, ctx):
            return ToolResult(ok=True, data={"res": 1})

    registry = ToolRegistry()
    registry.register(DummyTool())

    service = AgentService(llm=fake_llm, registry=registry, max_steps=4)
    reply = await service.chat("Sonsuz döngü", base_context)

    assert reply.kind == "fallback"
    assert len(fake_llm.calls) == 4


@pytest.mark.anyio
async def test_service_logging_hygiene(
    base_context: RequestContext,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO)
    fake_llm = FakeLLMProvider(responses=["Tamamdır."])
    registry = ToolRegistry()

    service = AgentService(llm=fake_llm, registry=registry)
    await service.chat("Sipariş no 100 nerede?", base_context)

    log_text = caplog.text
    # Log hijyeni kontrolü
    assert "Agent turn completed:" in log_text
    assert "user_id_hash=" in log_text
    # Ham soru metni ve ham user_id loglanmamalı
    assert "Sipariş no 100 nerede?" not in log_text
    assert "user-123" not in log_text


@pytest.mark.anyio
@pytest.mark.parametrize("empty_content", ["", "   ", "\n\t  \n"])
async def test_service_empty_or_whitespace_llm_response_returns_fallback(
    base_context: RequestContext,
    empty_content: str,
) -> None:
    """Model araç çağırmadan boş veya yalnızca boşluk döndüğünde kind='fallback' üretilmelidir."""
    fake_llm = FakeLLMProvider(responses=[empty_content])
    registry = ToolRegistry()

    service = AgentService(llm=fake_llm, registry=registry)
    reply = await service.chat("Merhaba", base_context)

    assert reply.kind == "fallback"
    assert reply.reply == service._fallback_message
    assert len(reply.reply) > 0
