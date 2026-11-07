"""HTTP client for order-service (:8082).

Enforces order ownership, parameter validation, and path injection defense.
"""

import re
import urllib.parse
from typing import Any
import httpx

from app.clients.base import DownstreamClient
from app.clients.models import OrderPage, OrderView
from app.core.config import settings

_ORDER_NUMBER_PATTERN = re.compile(r"^[A-Za-z0-9\-]{3,40}$")


class OrderClient(DownstreamClient):
    """Client for order query and cancellation endpoints."""

    def __init__(
        self,
        base_url: str | None = None,
        *,
        timeout_sec: float | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        url = base_url or settings.ORDER_SERVICE_URL
        super().__init__(url, timeout_sec=timeout_sec, transport=transport)

    def _validate_order_number(self, order_number: str) -> str:
        """Validate against path injection (../, query params, special chars)."""
        clean = order_number.strip()
        if not _ORDER_NUMBER_PATTERN.match(clean):
            raise ValueError(f"Geçersiz sipariş numarası biçimi: {clean}")
        return clean

    async def get_order_by_number(
        self,
        order_number: str,
        *,
        user_id: str,
        correlation_id: str | None = None,
    ) -> OrderView:
        """Retrieve customer order by human-readable order number (e.g. ORD-12345)."""
        valid_no = self._validate_order_number(order_number)
        encoded_no = urllib.parse.quote(valid_no)
        data = await self.get_json(
            f"/api/v1/orders/by-number/{encoded_no}",
            user_id=user_id,
            correlation_id=correlation_id,
        )
        return OrderView.model_validate(data)

    async def list_orders(
        self,
        customer_id: str,
        *,
        user_id: str,
        correlation_id: str | None = None,
        size: int = 5,
    ) -> OrderPage:
        """Retrieve paginated orders for the given customer ID (capped at 10 items)."""
        clamped_size = min(max(size, 1), 10)
        params: dict[str, Any] = {"page": 0, "size": clamped_size}
        encoded_cust_id = urllib.parse.quote(customer_id.strip())
        data = await self.get_json(
            f"/api/v1/orders/customer/{encoded_cust_id}",
            user_id=user_id,
            correlation_id=correlation_id,
            params=params,
        )
        if isinstance(data, dict):
            items_raw = data.get("content", [])
            total = data.get("totalElements", len(items_raw))
        elif isinstance(data, list):
            items_raw = data
            total = len(items_raw)
        else:
            items_raw = []
            total = 0

        items = [OrderView.model_validate(item) for item in items_raw]
        return OrderPage(items=items, total=total)

    async def cancel_order(
        self,
        order_id: str,
        reason: str,
        *,
        user_id: str,
        correlation_id: str | None = None,
    ) -> OrderView:
        """Request order cancellation with a reason. Initiates compensating Saga transactions."""
        encoded_id = urllib.parse.quote(order_id.strip())
        data = await self.post_json(
            f"/api/v1/orders/{encoded_id}/cancel",
            body={"reason": reason},
            user_id=user_id,
            correlation_id=correlation_id,
        )
        return OrderView.model_validate(data)
