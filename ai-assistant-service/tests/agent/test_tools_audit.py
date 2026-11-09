"""ToolRegistry audit kayıtları ve enumeration alarmı testleri."""

import json
from typing import Any
import httpx
import pytest

from app.agent.tools.base import ToolContext
from app.agent.tools.orders import GetOrderTool
from app.agent.tools.registry import ToolRegistry
from app.clients.base import DownstreamUnavailable
from app.clients.order import OrderClient
from app.core.audit import DenyTracker

USER_A = "11111111-1111-1111-1111-111111111111"
USER_B = "22222222-2222-2222-2222-222222222222"


def _create_mock_order_client(handler) -> OrderClient:
    return OrderClient(
        base_url="http://order-test",
        transport=httpx.MockTransport(handler),
    )


@pytest.mark.anyio
async def test_successful_tool_call_writes_ok_record(audit_records: list[dict[str, Any]]) -> None:
    """1. Kendi siparişi başarıyla sorgulandığında audit'e outcome='ok' tek satır yazılır."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "id": "1001",
                "orderNumber": "ORD-1",
                "customerId": USER_A,
                "status": "CONFIRMED",
                "totalAmount": 100.0,
                "items": [],
                "createdAt": "2026-11-01T10:00:00Z",
                "updatedAt": "2026-11-01T10:00:00Z",
            },
        )

    order_client = _create_mock_order_client(handler)
    registry = ToolRegistry()
    registry.register(GetOrderTool(order_client=order_client))

    ctx = ToolContext(user_id=USER_A, correlation_id="corr-1", question="Siparişim nerede?")
    result = await registry.execute("get_order", {"order_number": "ORD-1"}, ctx)

    assert result.ok is True
    tool_audits = [r for r in audit_records if r.get("event") == "tool_call"]
    assert len(tool_audits) == 1
    record = tool_audits[0]
    assert record["outcome"] == "ok"
    assert record["tool"] == "get_order"
    assert record["arg_names"] == ["order_number"]
    assert len(record["args_hash"]) == 16
    assert record["user_id"] == USER_A
    assert record["correlation_id"] == "corr-1"


@pytest.mark.anyio
async def test_foreign_order_returns_denied_when_downstream_403(audit_records: list[dict[str, Any]]) -> None:
    """2. Downstream 403 Forbidden döndüğünde modele 'Sipariş bulunamadı.', audit'e 'denied' düşer."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={"detail": "Access denied"})

    order_client = _create_mock_order_client(handler)
    registry = ToolRegistry()
    registry.register(GetOrderTool(order_client=order_client))

    ctx = ToolContext(user_id=USER_A, correlation_id="corr-2", question="Başkasının siparişi")
    result = await registry.execute("get_order", {"order_number": "ORD-B"}, ctx)

    assert result.ok is False
    assert result.error == "Sipariş bulunamadı."
    assert result.reason == "denied"

    tool_audits = [r for r in audit_records if r.get("event") == "tool_call"]
    assert len(tool_audits) == 1
    assert tool_audits[0]["outcome"] == "denied"


@pytest.mark.anyio
async def test_foreign_order_returns_ownership_mismatch_when_downstream_returns_other_customer(
    audit_records: list[dict[str, Any]],
) -> None:
    """3. Downstream hatalı olarak başka müşterinin siparişini dönerse Python sahiplik kontrolü yakalar ve outcome='ownership_mismatch' olur."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "id": "1002",
                "orderNumber": "ORD-B",
                "customerId": USER_B,  # Başka müşteri!
                "status": "CONFIRMED",
                "totalAmount": 200.0,
                "items": [],
                "createdAt": "2026-11-01T10:00:00Z",
                "updatedAt": "2026-11-01T10:00:00Z",
            },
        )

    order_client = _create_mock_order_client(handler)
    registry = ToolRegistry()
    registry.register(GetOrderTool(order_client=order_client))

    ctx = ToolContext(user_id=USER_A, correlation_id="corr-3", question="Sipariş")
    result = await registry.execute("get_order", {"order_number": "ORD-B"}, ctx)

    assert result.ok is False
    assert result.error == "Sipariş bulunamadı."
    assert result.reason == "ownership_mismatch"

    tool_audits = [r for r in audit_records if r.get("event") == "tool_call"]
    assert len(tool_audits) == 1
    assert tool_audits[0]["outcome"] == "ownership_mismatch"


@pytest.mark.anyio
async def test_not_found_and_denied_return_identical_model_error() -> None:
    """4. 404 ve 403 için modele/kullanıcıya dönen ToolResult.error metni tamamen aynıdır (varlık sızdırmaz)."""
    # 404
    client_404 = _create_mock_order_client(lambda r: httpx.Response(404, json={"detail": "Not found"}))
    reg_404 = ToolRegistry()
    reg_404.register(GetOrderTool(order_client=client_404))

    # 403
    client_403 = _create_mock_order_client(lambda r: httpx.Response(403, json={"detail": "Forbidden"}))
    reg_403 = ToolRegistry()
    reg_403.register(GetOrderTool(order_client=client_403))

    ctx = ToolContext(user_id=USER_A, correlation_id=None, question="q")
    res_404 = await reg_404.execute("get_order", {"order_number": "ORD-NONE"}, ctx)
    res_403 = await reg_403.execute("get_order", {"order_number": "ORD-OTHER"}, ctx)

    assert res_404.error == res_403.error == "Sipariş bulunamadı."
    assert res_404.reason == "not_found"
    assert res_403.reason == "denied"


@pytest.mark.anyio
async def test_invalid_args_writes_invalid_args_record(audit_records: list[dict[str, Any]]) -> None:
    """5. extra='forbid' ile engellenen parametre veya hatalı argüman durumunda outcome='invalid_args' yazılır."""
    order_client = _create_mock_order_client(lambda r: httpx.Response(200))
    registry = ToolRegistry()
    registry.register(GetOrderTool(order_client=order_client))

    ctx = ToolContext(user_id=USER_A, correlation_id="c-5", question="q")
    result = await registry.execute(
        "get_order",
        {"order_number": "ORD-1", "customer_id": "baskasi"},
        ctx,
    )

    assert result.ok is False
    assert result.reason == "invalid_args"

    tool_audits = [r for r in audit_records if r.get("event") == "tool_call"]
    assert len(tool_audits) == 1
    assert tool_audits[0]["outcome"] == "invalid_args"
    assert tool_audits[0]["arg_names"] == ["customer_id", "order_number"]


@pytest.mark.anyio
async def test_audit_record_never_contains_raw_arg_values(audit_records: list[dict[str, Any]]) -> None:
    """6. Audit kayıtlarının çıktısında parametre değerleri (sipariş no, hassas girdi) asla yer almaz."""
    secret_order = "ORD-SECRET-77"
    order_client = _create_mock_order_client(lambda r: httpx.Response(404))
    registry = ToolRegistry()
    registry.register(GetOrderTool(order_client=order_client))

    ctx = ToolContext(user_id=USER_A, correlation_id=None, question="q")
    await registry.execute("get_order", {"order_number": secret_order}, ctx)

    serialized = json.dumps(audit_records)
    assert secret_order not in serialized


@pytest.mark.anyio
async def test_downstream_unavailable_writes_unavailable_and_reraises(
    audit_records: list[dict[str, Any]],
) -> None:
    """7. Downstream 503 döndüğünde audit kaydı 'unavailable' yazılır ve DownstreamUnavailable yükselir."""
    order_client = _create_mock_order_client(lambda r: httpx.Response(503, json={"detail": "Service down"}))
    registry = ToolRegistry()
    registry.register(GetOrderTool(order_client=order_client))

    ctx = ToolContext(user_id=USER_A, correlation_id="c-7", question="q")
    with pytest.raises(DownstreamUnavailable):
        await registry.execute("get_order", {"order_number": "ORD-1"}, ctx)

    tool_audits = [r for r in audit_records if r.get("event") == "tool_call"]
    assert len(tool_audits) == 1
    assert tool_audits[0]["outcome"] == "unavailable"


@pytest.mark.anyio
async def test_every_call_has_correlation_id_and_user_id(audit_records: list[dict[str, Any]]) -> None:
    """8. Her tool audit kaydı ToolContext'teki user_id ve correlation_id'yi aynen taşır."""
    order_client = _create_mock_order_client(lambda r: httpx.Response(404))
    registry = ToolRegistry()
    registry.register(GetOrderTool(order_client=order_client))

    ctx = ToolContext(user_id=USER_A, correlation_id="tracking-corr-999", question="q")
    await registry.execute("get_order", {"order_number": "ORD-999"}, ctx)

    tool_audits = [r for r in audit_records if r.get("event") == "tool_call"]
    assert len(tool_audits) == 1
    assert tool_audits[0]["user_id"] == USER_A
    assert tool_audits[0]["correlation_id"] == "tracking-corr-999"


@pytest.mark.anyio
async def test_repeated_denials_emit_single_enumeration_alert(
    audit_records: list[dict[str, Any]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """9. Eşik 3 olan sayaçla aynı kullanıcı 5 kez reddedilirse tam 1 kez enumeration_suspected alarmı üretilir."""
    mock_tracker = DenyTracker(threshold=3, window_sec=60.0)
    monkeypatch.setattr("app.core.audit._deny_tracker", mock_tracker)

    order_client = _create_mock_order_client(lambda r: httpx.Response(403))
    registry = ToolRegistry()
    registry.register(GetOrderTool(order_client=order_client))

    ctx = ToolContext(user_id=USER_A, correlation_id="corr-enum", question="q")
    for i in range(5):
        await registry.execute("get_order", {"order_number": f"ORD-{i}"}, ctx)

    tool_calls = [r for r in audit_records if r.get("event") == "tool_call"]
    alerts = [r for r in audit_records if r.get("event") == "enumeration_suspected"]

    assert len(tool_calls) == 5
    assert len(alerts) == 1
    assert alerts[0]["outcome"] == "alert"
    assert alerts[0]["user_id"] == USER_A


@pytest.mark.anyio
async def test_denials_of_different_users_do_not_trigger_alert(
    audit_records: list[dict[str, Any]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """10. Farklı kullanıcıların birer kez reddedilmesi enumeration alarmını tetiklemez."""
    mock_tracker = DenyTracker(threshold=3, window_sec=60.0)
    monkeypatch.setattr("app.core.audit._deny_tracker", mock_tracker)

    order_client = _create_mock_order_client(lambda r: httpx.Response(403))
    registry = ToolRegistry()
    registry.register(GetOrderTool(order_client=order_client))

    for uid in ["usr-1", "usr-2", "usr-3"]:
        ctx = ToolContext(user_id=uid, correlation_id=None, question="q")
        await registry.execute("get_order", {"order_number": "ORD-1"}, ctx)

    alerts = [r for r in audit_records if r.get("event") == "enumeration_suspected"]
    assert len(alerts) == 0


@pytest.mark.anyio
async def test_successful_calls_do_not_count_toward_enumeration(
    audit_records: list[dict[str, Any]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """11. Başarılı tool çağrıları reddedilen erişim sayacına katılmaz ve alarm üretmez."""
    mock_tracker = DenyTracker(threshold=3, window_sec=60.0)
    monkeypatch.setattr("app.core.audit._deny_tracker", mock_tracker)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "id": "1001",
                "orderNumber": "ORD-OK",
                "customerId": USER_A,
                "status": "CONFIRMED",
                "totalAmount": 50.0,
                "items": [],
                "createdAt": "2026-11-01T10:00:00Z",
                "updatedAt": "2026-11-01T10:00:00Z",
            },
        )

    order_client = _create_mock_order_client(handler)
    registry = ToolRegistry()
    registry.register(GetOrderTool(order_client=order_client))

    ctx = ToolContext(user_id=USER_A, correlation_id=None, question="q")
    for _ in range(10):
        await registry.execute("get_order", {"order_number": "ORD-OK"}, ctx)

    alerts = [r for r in audit_records if r.get("event") == "enumeration_suspected"]
    assert len(alerts) == 0
