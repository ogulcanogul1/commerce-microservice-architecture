"""HTTP client for shipping-service (:8085).

Safely fetches parcel delivery progress by order ID after order ownership has been verified.
"""

import urllib.parse
import httpx

from app.clients.base import DownstreamClient, DownstreamNotFound
from app.clients.models import ShipmentView
from app.core.config import settings


class ShippingClient(DownstreamClient):
    """Client for parcel tracking and shipment query endpoints."""

    def __init__(
        self,
        base_url: str | None = None,
        *,
        timeout_sec: float | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        url = base_url or settings.SHIPPING_SERVICE_URL
        super().__init__(url, timeout_sec=timeout_sec, transport=transport)

    async def get_shipment_by_order(
        self,
        order_id: str,
        *,
        user_id: str,
        correlation_id: str | None = None,
    ) -> ShipmentView | None:
        """Fetch shipment associated with the specified order ID. Returns None if 404."""
        encoded_order_id = urllib.parse.quote(order_id.strip())
        try:
            data = await self.get_json(
                f"/api/v1/shipments/order/{encoded_order_id}",
                user_id=user_id,
                correlation_id=correlation_id,
            )
        except DownstreamNotFound:
            return None

        if isinstance(data, list):
            if not data:
                return None
            # En yeni kargo kaydını seç
            return ShipmentView.model_validate(data[-1])

        return ShipmentView.model_validate(data)
