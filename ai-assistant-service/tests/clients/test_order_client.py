from decimal import Decimal
import httpx
import pytest

from app.clients.base import (
    DownstreamBadRequest,
    DownstreamForbidden,
    DownstreamNotFound,
    DownstreamUnavailable,
)
from app.clients.order import OrderClient


@pytest.mark.anyio
async def test_order_client_headers_and_successful_get_by_number() -> None:
    captured_headers: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal captured_headers
        captured_headers = dict(request.headers)
        return httpx.Response(
            200,
            json={
                "id": "11111111-1111-1111-1111-111111111111",
                "orderNumber": "ORD-12345",
                "customerId": "22222222-2222-2222-2222-222222222222",
                "status": "CONFIRMED",
                "totalAmount": 1500.50,
                "currency": "TRY",
                "shippingAddress": "Gizli Adres Mah. No:1 Istanbul",  # PII alan
                "failureReason": None,
                "correlationId": "33333333-3333-3333-3333-333333333333",
                "items": [
                    {
                        "id": "44444444-4444-4444-4444-444444444444",
                        "sku": "SKU-KULAKLIK-1",
                        "productName": "Bluetooth Kulaklık",
                        "unitPrice": 1500.50,
                        "quantity": 1,
                        "subtotal": 1500.50,
                    }
                ],
                "createdAt": "2026-11-01T10:00:00Z",
                "updatedAt": "2026-11-01T10:05:00Z",
            },
        )

    transport = httpx.MockTransport(handler)
    client = OrderClient(base_url="http://order-test:8082", transport=transport)

    order = await client.get_order_by_number(
        "ORD-12345",
        user_id="22222222-2222-2222-2222-222222222222",
        correlation_id="test-corr-id",
    )

    # Başlık denetimleri
    assert captured_headers.get("x-gateway-secret") == "dgl-internal-gateway-secret-token-2026"
    assert captured_headers.get("x-user-id") == "22222222-2222-2222-2222-222222222222"
    assert captured_headers.get("x-correlation-id") == "test-corr-id"
    # X-User-Roles kesinlikle gönderilmemeli!
    assert "x-user-roles" not in captured_headers

    # Model doğrulamaları
    assert order.order_number == "ORD-12345"
    assert order.customer_id == "22222222-2222-2222-2222-222222222222"
    assert order.status == "CONFIRMED"
    assert order.total_amount == Decimal("1500.50")
    assert len(order.items) == 1
    assert order.items[0].product_name == "Bluetooth Kulaklık"

    # PII izolasyonu: shippingAddress modelde yer almamalı
    assert not hasattr(order, "shipping_address")
    assert not hasattr(order, "shippingAddress")


@pytest.mark.anyio
@pytest.mark.parametrize(
    "status_code, expected_exc",
    [
        (404, DownstreamNotFound),
        (403, DownstreamForbidden),
        (500, DownstreamUnavailable),
        (503, DownstreamUnavailable),
    ],
)
async def test_order_client_error_status_mapping(
    status_code: int,
    expected_exc: type[Exception],
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, json={"message": "Hata oluştu"})

    transport = httpx.MockTransport(handler)
    client = OrderClient(base_url="http://order-test:8082", transport=transport)

    with pytest.raises(expected_exc):
        await client.get_order_by_number("ORD-9999", user_id="user-1")


@pytest.mark.anyio
async def test_order_client_bad_request_carries_detail() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"detail": "Kargoya verilmiş sipariş iptal edilemez."})

    transport = httpx.MockTransport(handler)
    client = OrderClient(base_url="http://order-test:8082", transport=transport)

    with pytest.raises(DownstreamBadRequest) as exc_info:
        await client.cancel_order("order-123", reason="Vazgeçtim", user_id="user-1")

    assert "Kargoya verilmiş sipariş iptal edilemez." in exc_info.value.detail


@pytest.mark.anyio
async def test_order_client_get_retries_on_connection_error() -> None:
    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        raise httpx.ConnectError("Connection refused")

    transport = httpx.MockTransport(handler)
    client = OrderClient(base_url="http://order-test:8082", transport=transport)

    with pytest.raises(DownstreamUnavailable):
        await client.get_order_by_number("ORD-123", user_id="user-1")

    # GET isteği için tam 2 deneme yapılmalı (1 ilk + 1 retry)
    assert call_count == 2


@pytest.mark.anyio
async def test_order_client_post_does_not_retry_on_connection_error() -> None:
    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        raise httpx.ConnectError("Connection refused")

    transport = httpx.MockTransport(handler)
    client = OrderClient(base_url="http://order-test:8082", transport=transport)

    with pytest.raises(DownstreamUnavailable):
        await client.cancel_order("order-123", reason="İptal", user_id="user-1")

    # POST idempotent olmadığı için ASLA retry edilmemeli (tam 1 deneme)
    assert call_count == 1


@pytest.mark.anyio
@pytest.mark.parametrize(
    "malicious_order_number",
    [
        "../../actuator/env",
        "ORD-1?admin=true",
        "ORD;DROP TABLE orders",
        "AB",  # < 3 karakter
        "A" * 45,  # > 40 karakter
        "ORD 123",  # boşluk
    ],
)
async def test_order_client_path_injection_defense(malicious_order_number: str) -> None:
    # İsteğin downstream'e gitmediğini doğrulamak için boş mock
    transport = httpx.MockTransport(lambda req: httpx.Response(200))
    client = OrderClient(base_url="http://order-test:8082", transport=transport)

    with pytest.raises(ValueError, match="Geçersiz sipariş numarası biçimi"):
        await client.get_order_by_number(malicious_order_number, user_id="user-1")


@pytest.mark.anyio
async def test_order_client_list_orders_clamps_size() -> None:
    captured_params: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal captured_params
        captured_params = dict(request.url.params)
        return httpx.Response(
            200,
            json={
                "content": [
                    {
                        "id": "ord-1",
                        "orderNumber": "ORD-001",
                        "customerId": "cust-1",
                        "status": "PENDING",
                        "totalAmount": 100.0,
                        "currency": "TRY",
                        "items": [],
                        "createdAt": "2026-11-01T10:00:00Z",
                        "updatedAt": "2026-11-01T10:05:00Z",
                    }
                ],
                "totalElements": 1,
            },
        )

    transport = httpx.MockTransport(handler)
    client = OrderClient(base_url="http://order-test:8082", transport=transport)

    # 50 istense bile 10'a kırpılmalı
    page = await client.list_orders("cust-1", user_id="cust-1", size=50)

    assert captured_params.get("size") == "10"
    assert page.total == 1
    assert len(page.items) == 1
    assert page.items[0].order_number == "ORD-001"
