from datetime import datetime, timedelta, timezone
import json
import httpx
import pytest

from app.core.config import settings
from app.core.exceptions import (
    AccessDeniedException,
    ResourceNotFoundException,
    TransientException,
)
from app.core.security import RequestContext, _request_context_var, set_request_context
from app.tools import (
    CommerceHttpClient,
    set_http_client,
    tool_registry,
)
from app.tools.support_tools import set_escalation_publisher

CUSTOMER_ID = "11111111-1111-1111-1111-111111111111"
OTHER_CUSTOMER_ID = "99999999-9999-9999-9999-999999999999"
ORDER_ID = "22222222-2222-2222-2222-222222222222"


@pytest.fixture(autouse=True)
def authenticated_context():
    ctx = RequestContext(
        correlation_id="corr-test-123",
        user_id=CUSTOMER_ID,
        user_email="ayse.yilmaz@example.com",
        user_roles="ROLE_CUSTOMER",
    )
    token = set_request_context(ctx)
    yield ctx
    _request_context_var.reset(token)


def _create_mock_http_client(handler):
    transport = httpx.MockTransport(handler)
    client = CommerceHttpClient(transport=transport)
    set_http_client(client)
    return client


@pytest.mark.asyncio
async def test_commerce_http_client_propagates_headers_and_maps_errors():
    captured_headers = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured_headers.update(dict(request.headers))
        if request.url.path.endswith("/not-found"):
            return httpx.Response(404, json={"detail": "Order not found"})
        if request.url.path.endswith("/server-error"):
            return httpx.Response(503, json={"detail": "Database down"})
        return httpx.Response(200, json={"ok": True})

    client = _create_mock_http_client(handler)
    res = await client.get("http://localhost:8082/api/v1/orders/ok")
    assert res == {"ok": True}
    assert captured_headers["x-gateway-secret"] == settings.GATEWAY_INTERNAL_SECRET
    assert captured_headers["x-user-id"] == CUSTOMER_ID
    assert captured_headers["x-correlation-id"] == "corr-test-123"

    with pytest.raises(ResourceNotFoundException):
        await client.get("http://localhost:8082/api/v1/orders/not-found")

    with pytest.raises(TransientException):
        await client.get("http://localhost:8082/api/v1/orders/server-error")


@pytest.mark.asyncio
async def test_idor_protection_blocks_access_to_other_customers_order():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "id": ORDER_ID,
                "orderNumber": "ORD-9999",
                "customerId": OTHER_CUSTOMER_ID,
                "status": "CONFIRMED",
                "items": [],
            },
        )

    _create_mock_http_client(handler)
    with pytest.raises(AccessDeniedException):
        await tool_registry.execute("get_order_details", {"order_identifier": "ORD-9999"})


@pytest.mark.asyncio
async def test_scenario_a1_a2_a3_order_and_shipping_tools():
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/api/v1/orders/by-number/ORD-9912":
            return httpx.Response(
                200,
                json={
                    "id": ORDER_ID,
                    "orderNumber": "ORD-9912",
                    "customerId": CUSTOMER_ID,
                    "status": "CONFIRMED",
                    "totalAmount": 1750.0,
                    "currency": "TRY",
                    "shippingAddress": "Eski Ev Adresi Kadıköy",
                    "items": [
                        {
                            "id": "item-1",
                            "sku": "SKU-RED-SWEATER",
                            "productName": "Kırmızı Kazak",
                            "unitPrice": 750.0,
                            "quantity": 1,
                            "subtotal": 750.0,
                        },
                        {
                            "id": "item-2",
                            "sku": "SKU-BLUE-JEANS",
                            "productName": "Mavi Kot Pantolon",
                            "unitPrice": 1000.0,
                            "quantity": 1,
                            "subtotal": 1000.0,
                        },
                    ],
                },
            )
        if path == f"/api/v1/shipments/order/{ORDER_ID}":
            return httpx.Response(
                200,
                json={
                    "id": "ship-1",
                    "orderId": ORDER_ID,
                    "trackingNumber": "TRK-4421",
                    "carrier": "ARAS",
                    "status": "PENDING",
                    "estimatedDelivery": "2026-10-22T16:30:00Z",
                },
            )
        if path == "/api/v1/shipments/track/TRK-4421":
            return httpx.Response(
                200,
                json={
                    "trackingNumber": "TRK-4421",
                    "carrier": "ARAS",
                    "currentStatus": "IN_TRANSIT",
                    "estimatedDelivery": "2026-10-22T16:30:00Z",
                    "history": [{"status": "IN_TRANSIT", "description": "Kurye dağıtımda"}],
                },
            )
        return httpx.Response(404)

    _create_mock_http_client(handler)

    # A.1: Live shipment tracking
    track_res = await tool_registry.execute(
        "get_shipment_tracking", {"order_identifier": "ORD-9912"}
    )
    assert track_res["trackingNumber"] == "TRK-4421"
    assert track_res["carrier"] == "ARAS"
    assert track_res["currentStatus"] == "IN_TRANSIT"

    # A.2: Smart address change before courier dispatch
    addr_res = await tool_registry.execute(
        "update_order_shipping_address",
        {"order_identifier": "ORD-9912", "new_address": "Levent Ofis Plaza No:10 Beşiktaş"},
    )
    assert addr_res["addressUpdated"] is True
    assert addr_res["newAddress"] == "Levent Ofis Plaza No:10 Beşiktaş"

    # A.3: Partial item cancellation & Saga compensation
    cancel_res = await tool_registry.execute(
        "cancel_order_or_item",
        {
            "order_identifier": "ORD-9912",
            "reason": "Kırmızı kazağı istemiyorum",
            "item_sku": "Kırmızı Kazak",
        },
    )
    assert cancel_res["cancellationType"] == "PARTIAL_ITEM_CANCELLATION"
    assert cancel_res["refundAmount"] == 750.0
    assert cancel_res["remainingItemCount"] == 1


@pytest.mark.asyncio
async def test_scenario_b1_b2_b3_price_comparison_price_match_and_coupons():
    recent_purchase_time = (datetime.now(timezone.utc) - timedelta(hours=20)).isoformat()

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/api/v1/orders/by-number/ORD-SONY":
            return httpx.Response(
                200,
                json={
                    "id": ORDER_ID,
                    "orderNumber": "ORD-SONY",
                    "customerId": CUSTOMER_ID,
                    "status": "DELIVERED",
                    "currency": "TRY",
                    "createdAt": "2026-09-12T10:00:00Z",
                    "items": [
                        {
                            "sku": "SKU-SONY-WH1000XM5",
                            "productName": "Sony WH-1000XM5 Kulaklık",
                            "unitPrice": 9500.0,
                            "quantity": 1,
                        }
                    ],
                },
            )
        if path == "/api/v1/products/sku/SKU-SONY-WH1000XM5":
            return httpx.Response(
                200,
                json={
                    "sku": "SKU-SONY-WH1000XM5",
                    "name": "Sony WH-1000XM5 Kulaklık",
                    "basePrice": 11200.0,
                    "currency": "TRY",
                },
            )
        if path == "/api/v1/orders/by-number/ORD-COAT":
            return httpx.Response(
                200,
                json={
                    "id": ORDER_ID,
                    "orderNumber": "ORD-COAT",
                    "customerId": CUSTOMER_ID,
                    "status": "CONFIRMED",
                    "currency": "TRY",
                    "createdAt": recent_purchase_time,
                    "items": [
                        {
                            "sku": "SKU-WINTER-COAT",
                            "productName": "Kışlık Kaşe Mont",
                            "unitPrice": 2500.0,
                            "quantity": 1,
                        }
                    ],
                },
            )
        if path == "/api/v1/products/sku/SKU-WINTER-COAT":
            return httpx.Response(
                200,
                json={
                    "sku": "SKU-WINTER-COAT",
                    "name": "Kışlık Kaşe Mont",
                    "basePrice": 2000.0,
                    "currency": "TRY",
                },
            )
        return httpx.Response(404)

    _create_mock_http_client(handler)

    # B.1: Historical vs Current Price
    cmp_res = await tool_registry.execute(
        "compare_purchased_item_price",
        {"order_identifier": "ORD-SONY", "sku_or_product_name": "Sony"},
    )
    assert cmp_res["purchasedPrice"] == 9500.0
    assert cmp_res["currentCatalogPrice"] == 11200.0
    assert cmp_res["priceDifference"] == 1700.0
    assert cmp_res["percentageChange"] == 17.89

    # B.2: 48-Hour Price Match Guarantee Refund
    pm_res = await tool_registry.execute(
        "evaluate_price_match_refund",
        {"order_identifier": "ORD-COAT", "sku_or_product_name": "Mont"},
    )
    assert pm_res["eligible"] is True
    assert pm_res["refundAmount"] == 500.0

    # B.3: Cart Coupon Optimization
    coupon_res = await tool_registry.execute(
        "optimize_cart_coupons",
        {
            "cart_items": [
                {"name": "Ceket", "category": "giyim", "price": 1200.0, "quantity": 1},
                {"name": "Gömlek", "category": "giyim", "price": 600.0, "quantity": 1},
            ]
        },
    )
    assert coupon_res["originalCartTotal"] == 1800.0
    assert coupon_res["bestCoupon"]["couponCode"] == "MODA15"
    assert coupon_res["bestCoupon"]["discountAmount"] == 270.0


@pytest.mark.asyncio
async def test_scenario_c2_d1_e1_hardware_damage_and_escalation():
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/api/v1/products/sku/SKU-MB-DDR4":
            return httpx.Response(
                200,
                json={
                    "sku": "SKU-MB-DDR4",
                    "name": "B550 Anakart",
                    "attributes": {"socket": "AM4", "ram_type": "DDR4"},
                },
            )
        if path == "/api/v1/products/sku/SKU-RAM-DDR5":
            return httpx.Response(
                200,
                json={
                    "sku": "SKU-RAM-DDR5",
                    "name": "32GB 6000MHz RAM",
                    "attributes": {"ram_type": "DDR5"},
                },
            )
        if path == "/api/v1/orders/by-number/ORD-CUP":
            return httpx.Response(
                200,
                json={
                    "id": ORDER_ID,
                    "orderNumber": "ORD-CUP",
                    "customerId": CUSTOMER_ID,
                    "status": "DELIVERED",
                },
            )
        return httpx.Response(404)

    _create_mock_http_client(handler)

    # C.2: Hardware incompatibility detection (DDR4 motherboard vs DDR5 RAM)
    hw_res = await tool_registry.execute(
        "check_hardware_compatibility",
        {"skus": ["SKU-MB-DDR4", "SKU-RAM-DDR5"]},
    )
    assert hw_res["compatible"] is False
    assert len(hw_res["incompatibilityIssues"]) == 1

    # D.1: Multimodal damage return report
    dmg_res = await tool_registry.execute(
        "create_damage_return_report",
        {
            "order_identifier": "ORD-CUP",
            "item_description": "Porselen Fincan Takımı",
            "damage_summary": "Fincan kulpu kırık ve kutu ezilmiş",
            "damage_confidence_score": 0.98,
        },
    )
    assert dmg_res["status"] == "INSTANT_APPROVED"
    assert dmg_res["freeReturnCode"].startswith("#YRT-")

    # E.1: Human support escalation
    published_events = []

    async def fake_publisher(payload: dict):
        published_events.append(payload)

    set_escalation_publisher(fake_publisher)
    try:
        esc_res = await tool_registry.execute(
            "escalate_to_human_support",
            {
                "reason": "CUSTOMER_FRUSTRATION_AND_DELAYED_SHIPMENT",
                "chat_summary": "Müşterinin kargosu 3 gündür gecikmede, canlı temsilci talep etti.",
                "order_id": "ORD-9912",
            },
        )
        assert esc_res["escalated"] is True
        assert esc_res["ticketId"].startswith("SUP-")
        assert len(published_events) == 1
        assert published_events[0]["customerId"] == CUSTOMER_ID
    finally:
        set_escalation_publisher(None)
