"""Normalized domain views for downstream order and shipping services.

These models sanitize downstream responses by stripping raw addresses and PII,
ensuring that sensitive customer data is never passed to external LLMs.
"""

from datetime import datetime
from decimal import Decimal
from pydantic import BaseModel, ConfigDict, Field


class OrderItemView(BaseModel):
    """Sanitized item line within a customer order."""

    model_config = ConfigDict(frozen=True, extra="ignore", populate_by_name=True)

    product_name: str | None = Field(default=None, alias="productName")
    sku: str | None = Field(default=None)
    quantity: int = Field(default=1)


class OrderView(BaseModel):
    """Sanitized order view omitting postal addresses and correlation tracing IDs."""

    model_config = ConfigDict(frozen=True, extra="ignore", populate_by_name=True)

    id: str
    order_number: str = Field(alias="orderNumber")
    customer_id: str = Field(alias="customerId")
    status: str
    total_amount: Decimal = Field(alias="totalAmount")
    currency: str = Field(default="TRY")
    failure_reason: str | None = Field(default=None, alias="failureReason")
    items: list[OrderItemView] = Field(default_factory=list)
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")


class OrderPage(BaseModel):
    """Paginated collection of customer orders."""

    model_config = ConfigDict(frozen=True, extra="ignore", populate_by_name=True)

    items: list[OrderView] = Field(default_factory=list)
    total: int = Field(default=0)


class ShipmentEventView(BaseModel):
    """A milestone event in parcel delivery history."""

    model_config = ConfigDict(frozen=True, extra="ignore", populate_by_name=True)

    status: str
    description: str | None = Field(default=None)
    location: str | None = Field(default=None)
    occurred_at: datetime = Field(alias="eventTime")


class ShipmentView(BaseModel):
    """Sanitized parcel shipment view omitting recipient name and physical address."""

    model_config = ConfigDict(frozen=True, extra="ignore", populate_by_name=True)

    id: str
    order_id: str = Field(alias="orderId")
    customer_id: str | None = Field(default=None, alias="customerId")
    tracking_number: str = Field(alias="trackingNumber")
    carrier: str
    status: str
    estimated_delivery: datetime | None = Field(default=None, alias="estimatedDelivery")
    actual_delivery: datetime | None = Field(default=None, alias="actualDelivery")
    failure_reason: str | None = Field(default=None, alias="failureReason")
    events: list[ShipmentEventView] = Field(default_factory=list)
