from decimal import Decimal
import logging
from typing import Any
from unittest.mock import AsyncMock
import pytest
from datetime import datetime, timezone

from app.agent.executor import ActionExecutor
from app.agent.models import PendingAction
from app.clients.base import (
    DownstreamBadRequest,
    DownstreamForbidden,
    DownstreamNotFound,
)
from app.clients.models import OrderView
from app.core.security import RequestContext


def _make_order(order_number: str = "ORD-1", customer_id: str = "user-1", status: str = "PENDING") -> OrderView:
    return OrderView(
        id="ord-id-1",
        orderNumber=order_number,
        customerId=customer_id,
        status=status,
        totalAmount=Decimal("100"),
        currency="TRY",
        items=[],
        createdAt=datetime.now(timezone.utc),
        updatedAt=datetime.now(timezone.utc),
    )


@pytest.mark.anyio
async def test_executor_cancel_order_happy_path() -> None:
    mock_order = AsyncMock()
    mock_order.get_order_by_number.return_value = _make_order()
    mock_publisher = AsyncMock()

    executor = ActionExecutor(order_client=mock_order, ticket_publisher=mock_publisher)
    ctx = RequestContext(user_id="user-1", correlation_id="c-1")

    action = PendingAction(
        action_id="act-1",
        user_id="user-1",
        action_type="cancel_order",
        params={"order_id": "ord-id-1", "order_number": "ORD-1", "reason": "İptal isteği"},
        summary="İptal onayı?",
        created_at=datetime.now(timezone.utc),
        expires_at=datetime.now(timezone.utc),
    )

    result = await executor.execute(action, ctx)

    assert result.ok is True
    assert "başarıyla iptal edildi" in result.message
    # cancel_order tam 1 kez çağrıldı
    mock_order.cancel_order.assert_called_once_with(
        order_id="ord-id-1",
        reason="İptal isteği",
        user_id="user-1",
        correlation_id="c-1",
    )


@pytest.mark.anyio
async def test_executor_cancel_order_already_cancelled_skips_post() -> None:
    mock_order = AsyncMock()
    mock_order.get_order_by_number.return_value = _make_order(status="CANCELLED")
    mock_publisher = AsyncMock()

    executor = ActionExecutor(order_client=mock_order, ticket_publisher=mock_publisher)
    ctx = RequestContext(user_id="user-1", correlation_id=None)

    action = PendingAction(
        action_id="act-1",
        user_id="user-1",
        action_type="cancel_order",
        params={"order_id": "ord-id-1", "order_number": "ORD-1", "reason": "İptal"},
        summary="İptal?",
        created_at=datetime.now(timezone.utc),
        expires_at=datetime.now(timezone.utc),
    )

    result = await executor.execute(action, ctx)

    assert result.ok is True
    assert "zaten iptal edilmiş" in result.message
    # POST çağrısı yapılmamalı!
    mock_order.cancel_order.assert_not_called()


@pytest.mark.anyio
async def test_executor_cancel_order_ownership_mismatch(audit_records: list[dict[str, Any]]) -> None:
    mock_order = AsyncMock()
    # Farklı müşterinin siparişi
    mock_order.get_order_by_number.return_value = _make_order(customer_id="other-user")
    mock_publisher = AsyncMock()

    executor = ActionExecutor(order_client=mock_order, ticket_publisher=mock_publisher)
    ctx = RequestContext(user_id="user-1", correlation_id=None)

    action = PendingAction(
        action_id="act-1",
        user_id="user-1",
        action_type="cancel_order",
        params={"order_id": "ord-id-1", "order_number": "ORD-1", "reason": "İptal"},
        summary="İptal?",
        created_at=datetime.now(timezone.utc),
        expires_at=datetime.now(timezone.utc),
    )

    result = await executor.execute(action, ctx)

    assert result.ok is False
    assert result.message == "Sipariş bulunamadı."
    mock_order.cancel_order.assert_not_called()

    ownership_audits = [r for r in audit_records if r.get("event") == "ownership_check"]
    assert len(ownership_audits) == 1
    assert ownership_audits[0]["outcome"] == "ownership_mismatch"
    assert ownership_audits[0]["action_type"] == "cancel_order"
    assert ownership_audits[0]["user_id"] == "user-1"


@pytest.mark.anyio
async def test_executor_cancel_order_downstream_bad_request() -> None:
    mock_order = AsyncMock()
    mock_order.get_order_by_number.return_value = _make_order()
    mock_order.cancel_order.side_effect = DownstreamBadRequest("SHIPPING_CREATED state cannot be cancelled")
    mock_publisher = AsyncMock()

    executor = ActionExecutor(order_client=mock_order, ticket_publisher=mock_publisher)
    ctx = RequestContext(user_id="user-1", correlation_id=None)

    action = PendingAction(
        action_id="act-1",
        user_id="user-1",
        action_type="cancel_order",
        params={"order_id": "ord-id-1", "order_number": "ORD-1", "reason": "İptal"},
        summary="İptal?",
        created_at=datetime.now(timezone.utc),
        expires_at=datetime.now(timezone.utc),
    )

    result = await executor.execute(action, ctx)

    assert result.ok is False
    assert result.message == "Bu sipariş mevcut durumunda iptal edilemiyor."
    # Ham teknik detay müşteriye sızdırılmamalı
    assert "SHIPPING_CREATED" not in result.message


@pytest.mark.anyio
async def test_executor_cancel_order_downstream_forbidden(
    audit_records: list[dict[str, Any]], monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    mock_order = AsyncMock()
    mock_order.get_order_by_number.side_effect = DownstreamForbidden("Access denied")
    mock_publisher = AsyncMock()

    executor = ActionExecutor(order_client=mock_order, ticket_publisher=mock_publisher)
    ctx = RequestContext(user_id="secret-user-42", correlation_id="c-forbidden")

    action = PendingAction(
        action_id="act-1",
        user_id="secret-user-42",
        action_type="cancel_order",
        params={"order_id": "ord-id-1", "order_number": "ORD-1", "reason": "İptal"},
        summary="İptal?",
        created_at=datetime.now(timezone.utc),
        expires_at=datetime.now(timezone.utc),
    )

    with caplog.at_level(logging.WARNING):
        result = await executor.execute(action, ctx)

    assert result.ok is False
    assert result.message == "Sipariş bulunamadı."

    # Raw user_id must NOT be logged in service warning logs; user_id_hash is logged instead
    executor_logs = "\n".join(r.getMessage() for r in caplog.records if r.name != "audit")
    assert "secret-user-42" not in executor_logs
    assert "user_id_hash=" in executor_logs

    ownership_audits = [r for r in audit_records if r.get("event") == "ownership_check"]
    assert len(ownership_audits) == 1
    assert ownership_audits[0]["outcome"] == "denied"
    assert ownership_audits[0]["action_type"] == "cancel_order"
    assert ownership_audits[0]["user_id"] == "secret-user-42"


@pytest.mark.anyio
async def test_executor_cancel_order_downstream_not_found(
    audit_records: list[dict[str, Any]], monkeypatch: pytest.MonkeyPatch
) -> None:
    mock_order = AsyncMock()
    mock_order.get_order_by_number.side_effect = DownstreamNotFound("Order not found")
    mock_publisher = AsyncMock()

    executor = ActionExecutor(order_client=mock_order, ticket_publisher=mock_publisher)
    ctx = RequestContext(user_id="user-1", correlation_id="c-notfound")

    action = PendingAction(
        action_id="act-1",
        user_id="user-1",
        action_type="cancel_order",
        params={"order_id": "ord-id-1", "order_number": "ORD-1", "reason": "İptal"},
        summary="İptal?",
        created_at=datetime.now(timezone.utc),
        expires_at=datetime.now(timezone.utc),
    )

    result = await executor.execute(action, ctx)

    assert result.ok is False
    assert "Sipariş bulunamadı" in result.message

    ownership_audits = [r for r in audit_records if r.get("event") == "ownership_check"]
    assert len(ownership_audits) == 1
    assert ownership_audits[0]["outcome"] == "not_found"
    assert ownership_audits[0]["action_type"] == "cancel_order"
    assert ownership_audits[0]["user_id"] == "user-1"


@pytest.mark.anyio
async def test_executor_create_ticket_emits_unified_envelope() -> None:
    mock_order = AsyncMock()
    captured_event: dict = {}

    async def mock_publish(evt: dict) -> None:
        nonlocal captured_event
        captured_event = evt

    mock_publisher = AsyncMock()
    mock_publisher.publish = mock_publish

    executor = ActionExecutor(order_client=mock_order, ticket_publisher=mock_publisher)
    ctx = RequestContext(user_id="user-1", correlation_id="c-ticket")

    action = PendingAction(
        action_id="act-t",
        user_id="user-1",
        action_type="create_support_ticket",
        params={
            "subject": "Kırık ürün geldi",
            "summary": "Kargo kutusunu açtığımda ürün kırıktı. Tel: 0532 123 45 67",
            "order_number": "ORD-100",
        },
        summary="Destek talebi açılsın mı?",
        created_at=datetime.now(timezone.utc),
        expires_at=datetime.now(timezone.utc),
    )

    result = await executor.execute(action, ctx)

    assert result.ok is True
    assert "Destek talebiniz oluşturuldu" in result.message

    # Unified Event Envelope doğrulaması
    assert captured_event["eventType"] == "support.ticket.created"
    assert captured_event["aggregateType"] == "SupportTicket"
    assert captured_event["version"] == 1
    assert captured_event["correlationId"] == "c-ticket"
    assert captured_event["payload"]["customerId"] == "user-1"
    assert captured_event["payload"]["orderNumber"] == "ORD-100"
    # PII maskeleme kontrolü: Telefon maskelenmiş olmalı
    assert "[TELEFON]" in captured_event["payload"]["summary"]
    assert "0532" not in captured_event["payload"]["summary"]
