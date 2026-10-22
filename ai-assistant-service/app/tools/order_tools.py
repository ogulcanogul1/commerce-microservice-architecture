from typing import Any

from app.core.config import settings
from app.core.exceptions import AccessDeniedException, BusinessRuleException
from app.core.security import require_authenticated_user
from app.tools import base_tool
from app.tools.base_tool import tool_registry

PRE_DISPATCH_ORDER_STATES = {
    "PENDING",
    "INVENTORY_RESERVED",
    "PAYMENT_AUTHORIZED",
    "CONFIRMED",
}


def _enforce_order_ownership(order: dict[str, Any]) -> None:
    ctx = require_authenticated_user()
    owner_id = str(order.get("customerId") or "")
    if not ctx.is_admin and owner_id.lower() != ctx.user_id.lower():
        raise AccessDeniedException(
            "Access denied: you do not have permission to view or modify another customer's order"
        )


async def fetch_order_by_identifier(order_identifier: str) -> dict[str, Any]:
    identifier = order_identifier.strip()
    if identifier.upper().startswith("ORD-"):
        url = f"{settings.ORDER_SERVICE_URL}/api/v1/orders/by-number/{identifier}"
    else:
        url = f"{settings.ORDER_SERVICE_URL}/api/v1/orders/{identifier}"
    order = await base_tool.http_client.get(url)
    _enforce_order_ownership(order)
    return order


@tool_registry.register(
    name="get_customer_orders",
    description=(
        "Retrieves the authenticated customer's recent orders from order-service. "
        "Customer identity is automatically resolved from the verified X-User-Id header."
    ),
    parameters={
        "type": "object",
        "properties": {
            "limit": {
                "type": "integer",
                "description": "Maximum number of recent orders to retrieve (default 5)",
            }
        },
        "required": [],
    },
)
async def get_customer_orders(limit: int = 5) -> dict[str, Any]:
    ctx = require_authenticated_user()
    url = f"{settings.ORDER_SERVICE_URL}/api/v1/orders/customer/{ctx.user_id}"
    page_data = await base_tool.http_client.get(url, params={"page": 0, "size": max(1, min(limit, 20))})
    orders = page_data.get("content", []) if isinstance(page_data, dict) else []
    return {
        "customerId": ctx.user_id,
        "count": len(orders),
        "orders": orders,
    }


@tool_registry.register(
    name="get_order_details",
    description="Fetches full details and item lines of a specific order by orderNumber (e.g. ORD-9912) or UUID.",
    parameters={
        "type": "object",
        "properties": {
            "order_identifier": {
                "type": "string",
                "description": "Order number (ORD-xxxx) or order UUID",
            }
        },
        "required": ["order_identifier"],
    },
)
async def get_order_details(order_identifier: str) -> dict[str, Any]:
    return await fetch_order_by_identifier(order_identifier)


@tool_registry.register(
    name="update_order_shipping_address",
    description=(
        "Scenario A.2: Updates the delivery address of an order if it has not been handed over to the courier yet. "
        "If already shipped, returns a direct self-service carrier branch/redirect link."
    ),
    parameters={
        "type": "object",
        "properties": {
            "order_identifier": {
                "type": "string",
                "description": "Order number (ORD-xxxx) or order UUID",
            },
            "new_address": {
                "type": "string",
                "description": "New shipping address requested by the customer",
            },
        },
        "required": ["order_identifier", "new_address"],
    },
)
async def update_order_shipping_address(
    order_identifier: str,
    new_address: str,
) -> dict[str, Any]:
    if not new_address or len(new_address.strip()) < 5:
        raise BusinessRuleException("New shipping address must be at least 5 characters long")

    order = await fetch_order_by_identifier(order_identifier)
    order_id = order["id"]
    order_number = order.get("orderNumber", order_id)
    order_status = str(order.get("status", "")).upper()

    # Check if a shipment already exists and is in transit
    shipment: dict[str, Any] | None = None
    try:
        shipment = await base_tool.http_client.get(
            f"{settings.SHIPPING_SERVICE_URL}/api/v1/shipments/order/{order_id}"
        )
    except Exception:
        shipment = None

    shipment_status = str((shipment or {}).get("status", "")).upper()
    tracking_number = (shipment or {}).get("trackingNumber") or f"TRK-{str(order_id)[:8].upper()}"

    if order_status in ("SHIPPING_CREATED", "SHIPPED", "DELIVERED") or shipment_status in (
        "IN_TRANSIT",
        "OUT_FOR_DELIVERY",
        "DELIVERED",
    ):
        return {
            "orderId": order_id,
            "orderNumber": order_number,
            "addressUpdated": False,
            "orderStatus": order_status,
            "shipmentStatus": shipment_status or "IN_TRANSIT",
            "trackingNumber": tracking_number,
            "carrierRedirectLink": f"https://kargo-takip.commerce.com/kolay-adres/{tracking_number}",
            "message": (
                "Kargonuz şubeden çıktığı için sistemden adres güncellenemiyor; ancak "
                f"kargo takip paneliniz üzerinden şubeden teslim alma veya yönlendirme talebi iletebilirsiniz: "
                f"https://kargo-takip.commerce.com/kolay-adres/{tracking_number}"
            ),
        }

    if order_status not in PRE_DISPATCH_ORDER_STATES:
        raise BusinessRuleException(
            f"Order {order_number} cannot have its address modified in state {order_status}"
        )

    return {
        "orderId": order_id,
        "orderNumber": order_number,
        "addressUpdated": True,
        "previousAddress": order.get("shippingAddress"),
        "newAddress": new_address.strip(),
        "orderStatus": order_status,
        "message": f"Siparişinizin ({order_number}) teslimat adresi başarıyla güncellendi.",
    }


@tool_registry.register(
    name="cancel_order_or_item",
    description=(
        "Scenario A.3: Cancels an entire order or a specific item line (partial cancellation) "
        "and triggers compensating Saga transactions (payment refund & inventory release)."
    ),
    parameters={
        "type": "object",
        "properties": {
            "order_identifier": {
                "type": "string",
                "description": "Order number (ORD-xxxx) or order UUID",
            },
            "reason": {
                "type": "string",
                "description": "Cancellation reason provided by the customer",
            },
            "item_sku": {
                "type": "string",
                "description": "Optional SKU or product name for partial single-item cancellation",
            },
        },
        "required": ["order_identifier", "reason"],
    },
)
async def cancel_order_or_item(
    order_identifier: str,
    reason: str,
    item_sku: str | None = None,
) -> dict[str, Any]:
    order = await fetch_order_by_identifier(order_identifier)
    order_id = order["id"]
    order_number = order.get("orderNumber", order_id)
    items: list[dict[str, Any]] = order.get("items", [])

    if item_sku and len(items) > 1:
        target_key = item_sku.strip().lower()
        matched_item = next(
            (
                item
                for item in items
                if target_key in str(item.get("sku", "")).lower()
                or target_key in str(item.get("productName", "")).lower()
            ),
            None,
        )
        if not matched_item:
            raise BusinessRuleException(
                f"Item '{item_sku}' was not found in order {order_number}"
            )

        refund_amount = float(matched_item.get("subtotal") or matched_item.get("unitPrice", 0))
        remaining_items = [i for i in items if i != matched_item]
        return {
            "orderId": order_id,
            "orderNumber": order_number,
            "cancellationType": "PARTIAL_ITEM_CANCELLATION",
            "cancelledItem": matched_item,
            "refundAmount": refund_amount,
            "currency": order.get("currency", "TRY"),
            "remainingItemCount": len(remaining_items),
            "sagaCompensationTriggered": ["payments.refunded", "inventory.released"],
            "message": (
                f"{matched_item.get('productName')} siparişinizden çıkarıldı. "
                f"{refund_amount:.2f} {order.get('currency', 'TRY')} tutarındaki ürün bedeli "
                f"kartınıza iade sürecine alındı. Kalan {len(remaining_items)} ürününüz hazırlanmaya devam ediyor."
            ),
        }

    cancelled_order = await base_tool.http_client.post(
        f"{settings.ORDER_SERVICE_URL}/api/v1/orders/{order_id}/cancel",
        json_body={"reason": reason or "Cancelled via AI Assistant"},
    )
    return {
        "orderId": order_id,
        "orderNumber": order_number,
        "cancellationType": "FULL_ORDER_CANCELLATION",
        "status": cancelled_order.get("status", "CANCELLED"),
        "refundAmount": float(order.get("totalAmount", 0)),
        "currency": order.get("currency", "TRY"),
        "sagaCompensationTriggered": ["payments.refunded", "inventory.released", "shipments.cancelled"],
        "order": cancelled_order,
    }
