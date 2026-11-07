"""Downstream microservice clients and models for ai-assistant-service."""

from app.clients.base import (
    DownstreamBadRequest,
    DownstreamClient,
    DownstreamError,
    DownstreamForbidden,
    DownstreamNotFound,
    DownstreamUnavailable,
)
from app.clients.models import (
    OrderItemView,
    OrderPage,
    OrderView,
    ShipmentEventView,
    ShipmentView,
)
from app.clients.order import OrderClient
from app.clients.shipping import ShippingClient

__all__ = [
    "DownstreamBadRequest",
    "DownstreamClient",
    "DownstreamError",
    "DownstreamForbidden",
    "DownstreamNotFound",
    "DownstreamUnavailable",
    "OrderItemView",
    "OrderPage",
    "OrderView",
    "ShipmentEventView",
    "ShipmentView",
    "OrderClient",
    "ShippingClient",
]
