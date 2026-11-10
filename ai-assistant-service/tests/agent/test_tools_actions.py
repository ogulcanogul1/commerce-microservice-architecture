from decimal import Decimal
from unittest.mock import AsyncMock
import pytest
from datetime import datetime, timezone

from app.agent.pending import InMemoryPendingActionStore
from app.agent.tools.actions import (
    RequestOrderCancellationArgs,
    RequestOrderCancellationTool,
    RequestSupportTicketArgs,
    RequestSupportTicketTool,
)
from app.agent.tools.base import ToolContext
from app.clients.models import OrderView


def _make_order(order_number: str = "ORD-1", customer_id: str = "user-1", status: str = "PENDING") -> OrderView:
    return OrderView(
        id="ord-uuid-1",
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
async def test_request_order_cancellation_tool_proposes_action_without_executing() -> None:
    mock_order = AsyncMock()
    mock_order.get_order_by_number.return_value = _make_order()
    store = InMemoryPendingActionStore()

    tool = RequestOrderCancellationTool(order_client=mock_order, action_store=store)
    ctx = ToolContext(user_id="user-1", correlation_id="c-1", question="iptal et")

    res = await tool.run(RequestOrderCancellationArgs(order_number="ORD-1", reason="Vazgeçtim"), ctx)

    assert res.ok is True
    assert res.pending_action is not None
    assert res.pending_action.action_type == "cancel_order"
    assert "ORD-1" in res.pending_action.summary
    assert res.data["mesaj"] == "Onay bekleniyor"

    # KRİTİK: cancel_order fonksiyonu ASLA çağrılmamalıdır!
    mock_order.cancel_order.assert_not_called()

    # Store'a eklenmiş olmalı
    consumed = store.consume(res.pending_action.action_id, user_id="user-1")
    assert consumed is not None


@pytest.mark.anyio
async def test_request_cancellation_tool_already_cancelled_no_action_created() -> None:
    mock_order = AsyncMock()
    mock_order.get_order_by_number.return_value = _make_order(status="CANCELLED")
    store = InMemoryPendingActionStore()

    tool = RequestOrderCancellationTool(order_client=mock_order, action_store=store)
    ctx = ToolContext(user_id="user-1", correlation_id=None, question="iptal")

    res = await tool.run(RequestOrderCancellationArgs(order_number="ORD-1", reason="Vazgeçtim"), ctx)

    assert res.ok is True
    assert res.pending_action is None
    assert "zaten iptal edilmiş" in res.data["mesaj"]


@pytest.mark.anyio
async def test_request_cancellation_tool_ownership_mismatch() -> None:
    mock_order = AsyncMock()
    mock_order.get_order_by_number.return_value = _make_order(customer_id="other-user")
    store = InMemoryPendingActionStore()

    tool = RequestOrderCancellationTool(order_client=mock_order, action_store=store)
    ctx = ToolContext(user_id="user-1", correlation_id=None, question="iptal")

    res = await tool.run(RequestOrderCancellationArgs(order_number="ORD-1", reason="İptal"), ctx)

    assert res.ok is False
    assert res.error == "Sipariş bulunamadı."
    assert res.pending_action is None


@pytest.mark.anyio
async def test_request_support_ticket_tool_masks_pii_and_stores_action() -> None:
    mock_order = AsyncMock()
    mock_order.get_order_by_number.return_value = _make_order()
    store = InMemoryPendingActionStore()

    tool = RequestSupportTicketTool(order_client=mock_order, action_store=store)
    ctx = ToolContext(user_id="user-1", correlation_id="c-ticket", question="temsilci")

    res = await tool.run(
        RequestSupportTicketArgs(
            subject="Gecikme şikayeti",
            summary="Kartım 4532 0151 1283 0366 çekildi ama ürün gelmedi",
            order_number="ORD-1",
        ),
        ctx,
    )

    assert res.ok is True
    assert res.pending_action is not None
    assert res.pending_action.action_type == "create_support_ticket"
    # PII maskeleme kontrolü
    assert "[KART]" in res.pending_action.params["summary"]
    assert "4532" not in res.pending_action.params["summary"]


@pytest.mark.anyio
async def test_request_order_cancellation_store_error_handles_without_name_error() -> None:
    """Store hata verdiğinde logger.exception çalışmalı ve NameError fırlatılmadan hata dönmelidir."""
    from unittest.mock import MagicMock

    mock_order = AsyncMock()
    mock_order.get_order_by_number.return_value = _make_order()
    broken_store = MagicMock()
    broken_store.create.side_effect = RuntimeError("Redis connection lost")

    tool = RequestOrderCancellationTool(order_client=mock_order, action_store=broken_store)
    ctx = ToolContext(user_id="user-1", correlation_id="c-err", question="iptal")

    res = await tool.run(RequestOrderCancellationArgs(order_number="ORD-1", reason="Vazgeçtim"), ctx)

    assert res.ok is False
    assert "İşlem onay kaydı oluşturulamadı" in res.error


@pytest.mark.anyio
async def test_request_order_cancellation_masks_pii_in_reason_and_summary() -> None:
    """İptal gerekçesindeki hassas veriler (telefon, e-posta) özette ve parametrede maskelenmelidir."""
    mock_order = AsyncMock()
    mock_order.get_order_by_number.return_value = _make_order()
    store = InMemoryPendingActionStore()

    tool = RequestOrderCancellationTool(order_client=mock_order, action_store=store)
    ctx = ToolContext(user_id="user-1", correlation_id="c-pii", question="iptal")

    res = await tool.run(
        RequestOrderCancellationArgs(
            order_number="ORD-1",
            reason="İletişim için test@example.com ve 0555 123 45 67 aranabilir",
        ),
        ctx,
    )

    assert res.ok is True
    assert res.pending_action is not None
    assert "test@example.com" not in res.pending_action.summary
    assert "[EPOSTA]" in res.pending_action.summary
    assert "[TELEFON]" in res.pending_action.summary
