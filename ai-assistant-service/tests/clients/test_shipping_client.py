import httpx
import pytest

from app.clients.base import DownstreamForbidden, DownstreamUnavailable
from app.clients.shipping import ShippingClient


@pytest.mark.anyio
async def test_shipping_client_headers_and_successful_get_by_order() -> None:
    captured_headers: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal captured_headers
        captured_headers = dict(request.headers)
        return httpx.Response(
            200,
            json={
                "id": "ship-1",
                "orderId": "ord-1",
                "trackingNumber": "TRK-987654",
                "carrier": "YURTICI_KARGO",
                "status": "IN_TRANSIT",
                "recipientName": "Ahmet Yılmaz",  # PII alan
                "deliveryAddress": "Örnek Mah. No:5 Izmir",  # PII alan
                "estimatedDelivery": "2026-11-05T18:00:00Z",
                "actualDelivery": None,
                "failureReason": None,
                "events": [
                    {
                        "id": "evt-1",
                        "status": "CREATED",
                        "description": "Kargo kaydı oluşturuldu",
                        "location": "Istanbul Aktarma",
                        "eventTime": "2026-11-02T09:00:00Z",
                    },
                    {
                        "id": "evt-2",
                        "status": "IN_TRANSIT",
                        "description": "Araç transfer merkezinden hareket etti",
                        "location": "Bursa Transfer",
                        "eventTime": "2026-11-03T04:00:00Z",
                    },
                ],
                "createdAt": "2026-11-02T09:00:00Z",
                "updatedAt": "2026-11-03T04:00:00Z",
            },
        )

    transport = httpx.MockTransport(handler)
    client = ShippingClient(base_url="http://shipping-test:8085", transport=transport)

    shipment = await client.get_shipment_by_order("ord-1", user_id="user-123")

    assert shipment is not None
    assert captured_headers.get("x-gateway-secret") == "dgl-internal-gateway-secret-token-2026"
    assert captured_headers.get("x-user-id") == "user-123"
    assert "x-user-roles" not in captured_headers

    assert shipment.tracking_number == "TRK-987654"
    assert shipment.carrier == "YURTICI_KARGO"
    assert shipment.status == "IN_TRANSIT"
    assert len(shipment.events) == 2
    assert shipment.events[1].status == "IN_TRANSIT"
    assert shipment.events[1].description == "Araç transfer merkezinden hareket etti"

    # PII izolasyonu: recipientName ve deliveryAddress modelde yer almamalı
    assert not hasattr(shipment, "recipient_name")
    assert not hasattr(shipment, "delivery_address")


@pytest.mark.anyio
async def test_shipping_client_404_returns_none() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"message": "Kargo bulunamadı"})

    transport = httpx.MockTransport(handler)
    client = ShippingClient(base_url="http://shipping-test:8085", transport=transport)

    result = await client.get_shipment_by_order("ord-not-found", user_id="user-1")
    assert result is None


@pytest.mark.anyio
async def test_shipping_client_forbidden_and_unavailable_raise() -> None:
    def forbidden_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={"message": "Yetkisiz erişim"})

    transport = httpx.MockTransport(forbidden_handler)
    client = ShippingClient(base_url="http://shipping-test:8085", transport=transport)

    with pytest.raises(DownstreamForbidden):
        await client.get_shipment_by_order("ord-forbidden", user_id="user-1")

    def error_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"message": "Sunucu hatası"})

    transport_err = httpx.MockTransport(error_handler)
    client_err = ShippingClient(base_url="http://shipping-test:8085", transport=transport_err)

    with pytest.raises(DownstreamUnavailable):
        await client_err.get_shipment_by_order("ord-error", user_id="user-1")


@pytest.mark.anyio
async def test_shipping_client_handles_list_response_picks_newest() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=[
                {
                    "id": "ship-old",
                    "orderId": "ord-1",
                    "trackingNumber": "TRK-OLD",
                    "carrier": "YURTICI_KARGO",
                    "status": "CANCELLED",
                    "events": [],
                },
                {
                    "id": "ship-new",
                    "orderId": "ord-1",
                    "trackingNumber": "TRK-NEW",
                    "carrier": "ARAS_KARGO",
                    "status": "IN_TRANSIT",
                    "events": [],
                },
            ],
        )

    transport = httpx.MockTransport(handler)
    client = ShippingClient(base_url="http://shipping-test:8085", transport=transport)

    shipment = await client.get_shipment_by_order("ord-1", user_id="user-1")
    assert shipment is not None
    assert shipment.id == "ship-new"
    assert shipment.tracking_number == "TRK-NEW"
