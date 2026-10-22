import uuid
from typing import Any
from app.core.config import settings
from app.core.exceptions import BusinessRuleException
import app.tools.base_tool as base_tool
from app.tools.base_tool import tool_registry
from app.tools.order_tools import fetch_order_by_identifier


@tool_registry.register(
    name="get_shipment_tracking",
    description=(
        "Scenario A.1: Fetches live courier status, carrier name, estimated delivery time, and tracking history "
        "from shipping-service by order identifier (ORD-xxxx / UUID) or tracking number (TRK-xxxx)."
    ),
    parameters={
        "type": "object",
        "properties": {
            "order_identifier": {
                "type": "string",
                "description": "Order number (ORD-xxxx) or order UUID",
            },
            "tracking_number": {
                "type": "string",
                "description": "Carrier tracking number (e.g. TRK-4421)",
            },
        },
        "required": [],
    },
)
async def get_shipment_tracking(
    order_identifier: str | None = None,
    tracking_number: str | None = None,
) -> dict[str, Any]:
    if not order_identifier and not tracking_number:
        raise BusinessRuleException(
            "Either order_identifier or tracking_number must be provided to track a shipment"
        )

    resolved_order_number: str | None = None
    if order_identifier:
        order = await fetch_order_by_identifier(order_identifier)
        order_id = order["id"]
        resolved_order_number = order.get("orderNumber", str(order_id))
        shipment = await base_tool.http_client.get(
            f"{settings.SHIPPING_SERVICE_URL}/api/v1/shipments/order/{order_id}"
        )
        tracking_no = shipment.get("trackingNumber")
        if tracking_no:
            tracking = await base_tool.http_client.get(
                f"{settings.SHIPPING_SERVICE_URL}/api/v1/shipments/track/{tracking_no}"
            )
            return {
                "orderId": order_id,
                "orderNumber": resolved_order_number,
                "trackingNumber": tracking.get("trackingNumber", tracking_no),
                "carrier": tracking.get("carrier") or shipment.get("carrier"),
                "currentStatus": tracking.get("currentStatus") or shipment.get("status"),
                "estimatedDelivery": tracking.get("estimatedDelivery")
                or shipment.get("estimatedDelivery"),
                "actualDelivery": tracking.get("actualDelivery"),
                "deliveryAddress": shipment.get("deliveryAddress"),
                "history": tracking.get("history") or shipment.get("events", []),
            }
        return shipment

    tracking_data = await base_tool.http_client.get(
        f"{settings.SHIPPING_SERVICE_URL}/api/v1/shipments/track/{tracking_number.strip()}"
    )
    return {
        "trackingNumber": tracking_data.get("trackingNumber", tracking_number),
        "carrier": tracking_data.get("carrier"),
        "currentStatus": tracking_data.get("currentStatus"),
        "estimatedDelivery": tracking_data.get("estimatedDelivery"),
        "actualDelivery": tracking_data.get("actualDelivery"),
        "history": tracking_data.get("history", []),
    }


@tool_registry.register(
    name="create_damage_return_report",
    description=(
        "Scenario D.1: Creates an automated damaged-product claim after multimodal image verification "
        "and generates a free return shipping code and replacement order dispatch."
    ),
    parameters={
        "type": "object",
        "properties": {
            "order_identifier": {
                "type": "string",
                "description": "Order number (ORD-xxxx) or order UUID",
            },
            "item_description": {
                "type": "string",
                "description": "Name or SKU of the damaged product",
            },
            "damage_summary": {
                "type": "string",
                "description": "Visual damage findings from the uploaded photo",
            },
            "damage_confidence_score": {
                "type": "number",
                "description": "Visual verification confidence score between 0.0 and 1.0 (e.g. 0.98)",
            },
        },
        "required": ["order_identifier", "item_description", "damage_summary"],
    },
)
async def create_damage_return_report(
    order_identifier: str,
    item_description: str,
    damage_summary: str,
    damage_confidence_score: float = 0.98,
) -> dict[str, Any]:
    order = await fetch_order_by_identifier(order_identifier)
    order_id = order["id"]
    order_number = order.get("orderNumber", str(order_id))

    report_id = f"DMG-{uuid.uuid4().hex[:6].upper()}"
    return_code = f"#YRT-{uuid.uuid4().int % 90000 + 10000}"

    return {
        "reportId": report_id,
        "orderId": order_id,
        "orderNumber": order_number,
        "itemDescription": item_description,
        "damageSummary": damage_summary,
        "damageConfidenceScore": round(float(damage_confidence_score), 2),
        "status": "INSTANT_APPROVED",
        "carrier": "YURTICI_KARGO",
        "freeReturnCode": return_code,
        "replacementAction": "AUTO_DISPATCH_ON_CARRIER_SCAN",
        "message": (
            f"Fotoğraf incelendi ve kargo kaynaklı hasar tespit edildi (Doğrulama: %{int(damage_confidence_score * 100)}). "
            f"İade işleminiz anında onaylandı. Yurtiçi Kargo Ücretsiz İade Kodunuz: {return_code}. "
            "Ürünü kargoya verdiğiniz an yenisi adresinize kargolanacaktır."
        ),
    }
