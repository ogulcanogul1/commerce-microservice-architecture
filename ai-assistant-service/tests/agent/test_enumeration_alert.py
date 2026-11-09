"""Enumeration (ID tarama) saldırısı uçtan uca tespit ve alarm testleri."""

from typing import Any
import httpx
import pytest

from app.agent.service import AgentService
from app.agent.tools.orders import GetOrderTool
from app.agent.tools.registry import ToolRegistry
from app.clients.order import OrderClient
from app.core.audit import DenyTracker
from app.core.security import RequestContext
from app.llm.base import ToolCallRequest
from app.llm.fake import FakeLLMProvider

USER_ATTACKER = "55555555-5555-5555-5555-555555555555"


@pytest.mark.anyio
async def test_enumeration_alert_end_to_end_denied_order_lookups(
    audit_records: list[dict[str, Any]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Saldırgan arka arkaya başkalarının siparişlerini denediğinde (downstream 403):
    1. Her tool çağrısı 'denied' olarak audit edilir.
    2. Eşik 5 aşıldığında tam 1 adet 'enumeration_suspected' alarmı üretilir.
    3. Kullanıcıya/modele dönen metinlerde hiçbir fark oluşmaz ('Sipariş bulunamadı.').
    """
    # Eşik 5, pencere 60 saniye
    tracker = DenyTracker(threshold=5, window_sec=60.0)
    monkeypatch.setattr("app.core.audit._deny_tracker", tracker)

    # Downstream tüm sorgulara 403 Forbidden döner
    mock_transport = httpx.MockTransport(lambda r: httpx.Response(403, json={"detail": "Access denied"}))
    order_client = OrderClient(base_url="http://order-test", transport=mock_transport)

    registry = ToolRegistry()
    registry.register(GetOrderTool(order_client=order_client))

    # 6 farklı sipariş için LLM yanıt dizisi (her tur için 1 tool çağrısı + 1 model nihai cevabı)
    llm_responses: list[Any] = []
    for i in range(1, 7):
        llm_responses.append(
            [
                ToolCallRequest(
                    call_id=f"call-enum-{i}",
                    tool_name="get_order",
                    arguments={"order_number": f"ORD-{i:03d}"},
                )
            ]
        )
        llm_responses.append("Sipariş bulunamadı.")

    fake_llm = FakeLLMProvider(responses=llm_responses)
    service = AgentService(llm=fake_llm, registry=registry)
    ctx = RequestContext(user_id=USER_ATTACKER, correlation_id="enum-attack-corr")

    # 6 ardışık sipariş sorgusu
    for i in range(1, 7):
        reply = await service.chat(f"ORD-{i:03d} nerede?", ctx)
        assert reply.kind == "answer"
        assert reply.reply == "Sipariş bulunamadı."

    # Kayıtları incele
    tool_calls = [r for r in audit_records if r.get("event") == "tool_call"]
    alerts = [r for r in audit_records if r.get("event") == "enumeration_suspected"]

    assert len(tool_calls) == 6
    for tc in tool_calls:
        assert tc["outcome"] == "denied"
        assert tc["user_id"] == USER_ATTACKER

    assert len(alerts) == 1
    alert = alerts[0]
    assert alert["outcome"] == "alert"
    assert alert["user_id"] == USER_ATTACKER
    assert alert["threshold"] == 5
