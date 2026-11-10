from decimal import Decimal
from unittest.mock import AsyncMock
import pytest
from datetime import datetime, timezone

from app.agent.tools.base import ToolContext
from app.agent.tools.shipping import GetShipmentArgs, GetShipmentTool
from app.clients.models import OrderItemView, OrderView, ShipmentEventView, ShipmentView


def _make_order(order_number: str = "ORD-12345", customer_id: str = "user-1") -> OrderView:
    return OrderView(
        id="ord-uuid-1",
        orderNumber=order_number,
        customerId=customer_id,
        status="CONFIRMED",
        totalAmount=Decimal("100"),
        currency="TRY",
        items=[],
        createdAt=datetime.now(timezone.utc),
        updatedAt=datetime.now(timezone.utc),
    )


def _make_shipment() -> ShipmentView:
    return ShipmentView(
        id="ship-uuid-1",
        orderId="ord-uuid-1",
        trackingNumber="TRK-123456",
        carrier="YURTICI_KARGO",
        status="IN_TRANSIT",
        estimatedDelivery=datetime(2026, 11, 10, 18, 0, tzinfo=timezone.utc),
        actualDelivery=None,
        failureReason=None,
        events=[
            ShipmentEventView(
                status="CREATED",
                description="Kargo teslim alındı",
                location="Şube",
                eventTime=datetime(2026, 11, 8, 10, 0, tzinfo=timezone.utc),
            )
        ],
    )


def test_shipping_tool_schema_has_no_forbidden_fields() -> None:
    tool = GetShipmentTool(order_client=AsyncMock(), shipping_client=AsyncMock())
    params = tool.definition().parameters
    forbidden = ["customer_id", "user_id", "userId", "customerId", "tracking_number"]
    props = params.get("properties", {})
    for f in forbidden:
        assert f not in props


@pytest.mark.anyio
async def test_get_shipment_tool_happy_path() -> None:
    mock_order = AsyncMock()
    mock_order.get_order_by_number.return_value = _make_order()
    mock_shipping = AsyncMock()
    mock_shipping.get_shipment_by_order.return_value = _make_shipment()

    tool = GetShipmentTool(order_client=mock_order, shipping_client=mock_shipping)
    ctx = ToolContext(user_id="user-1", correlation_id="c-1", question="kargom nerede")

    res = await tool.run(GetShipmentArgs(order_number="ORD-12345"), ctx)

    assert res.ok is True
    assert res.data["order_number"] == "ORD-12345"
    assert res.data["carrier"] == "YURTICI_KARGO"
    assert res.data["tracking_number"] == "TRK-123456"
    assert res.data["status"] == "IN_TRANSIT"
    assert "taşınıyor" in res.data["status_aciklama"]
    assert len(res.data["last_events"]) == 1

    # İki aşamalı çağrı doğrulandı:
    mock_order.get_order_by_number.assert_called_once_with(
        order_number="ORD-12345",
        user_id="user-1",
        correlation_id="c-1",
    )
    mock_shipping.get_shipment_by_order.assert_called_once_with(
        order_id="ord-uuid-1",
        user_id="user-1",
        correlation_id="c-1",
    )


@pytest.mark.anyio
async def test_get_shipment_tool_stops_if_order_ownership_fails() -> None:
    mock_order = AsyncMock()
    # Başka müşterinin siparişi
    mock_order.get_order_by_number.return_value = _make_order(customer_id="alien-user")
    mock_shipping = AsyncMock()

    tool = GetShipmentTool(order_client=mock_order, shipping_client=mock_shipping)
    ctx = ToolContext(user_id="user-1", correlation_id=None, question="ORD-12345")

    res = await tool.run(GetShipmentArgs(order_number="ORD-12345"), ctx)

    assert res.ok is False
    assert res.error == "Sipariş bulunamadı."
    # Kargo servisi KESİNLİKLE çağrılmamalı!
    mock_shipping.get_shipment_by_order.assert_not_called()


@pytest.mark.anyio
async def test_get_shipment_tool_when_no_shipment_yet() -> None:
    mock_order = AsyncMock()
    mock_order.get_order_by_number.return_value = _make_order()
    mock_shipping = AsyncMock()
    mock_shipping.get_shipment_by_order.return_value = None  # Henüz kargo kaydı yok

    tool = GetShipmentTool(order_client=mock_order, shipping_client=mock_shipping)
    ctx = ToolContext(user_id="user-1", correlation_id=None, question="ORD-12345")

    res = await tool.run(GetShipmentArgs(order_number="ORD-12345"), ctx)

    assert res.ok is True
    assert res.data["shipment"] is None
    assert "henüz kargo kaydı yok" in res.data["mesaj"]


@pytest.mark.anyio
async def test_get_shipment_tool_stops_if_shipment_customer_id_mismatch() -> None:
    """Kargo kaydındaki customerId kullanıcı ile uyuşmuyorsa savunma derinliği gereği reddedilir."""
    mock_order = AsyncMock()
    mock_order.get_order_by_number.return_value = _make_order(customer_id="user-1")

    # Kargo nesnesinde customerId başka kullanıcıya ait
    alien_shipment = _make_shipment()
    object.__setattr__(alien_shipment, "customer_id", "alien-user-999")

    mock_shipping = AsyncMock()
    mock_shipping.get_shipment_by_order.return_value = alien_shipment

    tool = GetShipmentTool(order_client=mock_order, shipping_client=mock_shipping)
    ctx = ToolContext(user_id="user-1", correlation_id=None, question="ORD-12345")

    res = await tool.run(GetShipmentArgs(order_number="ORD-12345"), ctx)

    assert res.ok is False
    assert res.error == "Sipariş bulunamadı."
    assert res.reason == "ownership_mismatch"
