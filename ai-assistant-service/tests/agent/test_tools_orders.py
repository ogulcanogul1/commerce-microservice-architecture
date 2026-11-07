from decimal import Decimal
from unittest.mock import AsyncMock
import pytest

from app.agent.tools.base import ToolContext
from app.agent.tools.orders import (
    GetOrderArgs,
    GetOrderTool,
    ListMyOrdersArgs,
    ListMyOrdersTool,
)
from app.clients.base import DownstreamNotFound
from app.clients.models import OrderItemView, OrderPage, OrderView
from datetime import datetime, timezone


def _make_sample_order(
    order_number: str = "ORD-12345",
    customer_id: str = "user-1",
    status: str = "CONFIRMED",
) -> OrderView:
    return OrderView(
        id="ord-uuid-1",
        orderNumber=order_number,
        customerId=customer_id,
        status=status,
        totalAmount=Decimal("250.75"),
        currency="TRY",
        failureReason=None,
        items=[
            OrderItemView(productName="Kitap", sku="SKU-1", quantity=1),
            OrderItemView(productName="Defter", sku="SKU-2", quantity=2),
        ],
        createdAt=datetime(2026, 11, 1, 10, 0, tzinfo=timezone.utc),
        updatedAt=datetime(2026, 11, 1, 10, 5, tzinfo=timezone.utc),
    )


@pytest.mark.parametrize(
    "tool_cls",
    [GetOrderTool, ListMyOrdersTool],
)
def test_order_tools_schemas_have_no_forbidden_identity_fields(tool_cls) -> None:
    # Sahte client ile instance al
    mock_client = AsyncMock()
    tool = tool_cls(order_client=mock_client)
    params = tool.definition().parameters

    forbidden = ["customer_id", "user_id", "userId", "customerId", "tracking_number"]
    props = params.get("properties", {})
    for f in forbidden:
        assert f not in props


@pytest.mark.anyio
async def test_get_order_tool_happy_path() -> None:
    mock_client = AsyncMock()
    mock_client.get_order_by_number.return_value = _make_sample_order()
    tool = GetOrderTool(order_client=mock_client)

    ctx = ToolContext(user_id="user-1", correlation_id="c-1", question="Siparişim nerede?")
    res = await tool.run(GetOrderArgs(order_number="ORD-12345"), ctx)

    assert res.ok is True
    assert res.data["order_number"] == "ORD-12345"
    assert res.data["status"] == "CONFIRMED"
    assert "onaylandı ve tamamlandı" in res.data["status_aciklama"]
    assert res.data["total_amount"] == 250.75
    assert len(res.data["items"]) == 2
    # PII kontrolü: adres veya correlation_id verisi tool çıktısında olmamalı
    assert "shipping_address" not in res.data
    assert "correlation_id" not in res.data


@pytest.mark.anyio
async def test_get_order_tool_defense_in_depth_ownership_mismatch() -> None:
    # Downstream hatalı davranıp başka birinin siparişini dönerse (user-2)
    mock_client = AsyncMock()
    mock_client.get_order_by_number.return_value = _make_sample_order(customer_id="user-2")
    tool = GetOrderTool(order_client=mock_client)

    ctx = ToolContext(user_id="user-1", correlation_id="c-1", question="ORD-12345")
    res = await tool.run(GetOrderArgs(order_number="ORD-12345"), ctx)

    # Savunma derinliği devreye girmeli ve 404 ile aynı hata dönmeli
    assert res.ok is False
    assert res.error == "Sipariş bulunamadı."


@pytest.mark.anyio
async def test_list_my_orders_tool_filters_alien_records() -> None:
    mock_client = AsyncMock()
    mock_client.list_orders.return_value = OrderPage(
        items=[
            _make_sample_order(order_number="ORD-1", customer_id="user-1"),
            _make_sample_order(order_number="ORD-2", customer_id="user-OTHER"),  # Başkasının
            _make_sample_order(order_number="ORD-3", customer_id="user-1"),
        ],
        total=3,
    )
    tool = ListMyOrdersTool(order_client=mock_client)

    ctx = ToolContext(user_id="user-1", correlation_id=None, question="siparişlerim")
    res = await tool.run(ListMyOrdersArgs(limit=5), ctx)

    assert res.ok is True
    # Başkasının siparişi ayıklanmış olmalı
    assert res.data["total"] == 2
    assert len(res.data["orders"]) == 2
    assert [o["order_number"] for o in res.data["orders"]] == ["ORD-1", "ORD-3"]
