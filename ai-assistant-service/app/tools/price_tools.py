from datetime import UTC, datetime
from typing import Any

from app.core.config import settings
from app.core.exceptions import BusinessRuleException
from app.tools import base_tool
from app.tools.base_tool import tool_registry
from app.tools.order_tools import fetch_order_by_identifier

PRICE_MATCH_WINDOW_HOURS = 48.0

ACTIVE_CAMPAIGNS = [
    {
        "code": "MODA15",
        "title": "Giyim Kategorisinde 200 TL Üzerine %15 İndirim",
        "type": "CATEGORY_PERCENT",
        "category": "giyim",
        "min_spend": 200.0,
        "percent": 15.0,
    },
    {
        "code": "TECH10",
        "title": "Elektronik Kategorisinde 1.000 TL Üzerine %10 İndirim (Maks 500 TL)",
        "type": "CATEGORY_PERCENT",
        "category": "elektronik",
        "min_spend": 1000.0,
        "percent": 10.0,
        "max_discount": 500.0,
    },
    {
        "code": "SEPET150",
        "title": "1.500 TL ve Üzeri Tüm Sepette 150 TL Anında İndirim",
        "type": "CART_FLAT",
        "min_spend": 1500.0,
        "flat_discount": 150.0,
    },
    {
        "code": "SUPER300",
        "title": "2.500 TL ve Üzeri Tüm Sepette 300 TL İndirim",
        "type": "CART_FLAT",
        "min_spend": 2500.0,
        "flat_discount": 300.0,
    },
]


def _parse_iso_datetime(value: str | None) -> datetime:
    if not value:
        return datetime.now(UTC)
    cleaned = value.replace("Z", "+00:00")
    dt = datetime.fromisoformat(cleaned)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt


def _match_order_item(order: dict[str, Any], sku_or_name: str) -> dict[str, Any]:
    items: list[dict[str, Any]] = order.get("items", [])
    if not items:
        raise BusinessRuleException(f"Order {order.get('orderNumber')} contains no items")
    needle = sku_or_name.strip().lower()
    for item in items:
        if needle in str(item.get("sku", "")).lower() or needle in str(item.get("productName", "")).lower():
            return item
    return items[0]


@tool_registry.register(
    name="compare_purchased_item_price",
    description=(
        "Scenario B.1: Compares the historical unitPrice paid by the customer in a past order "
        "against the current catalog basePrice in product-service."
    ),
    parameters={
        "type": "object",
        "properties": {
            "order_identifier": {
                "type": "string",
                "description": "Order number (ORD-xxxx) or order UUID",
            },
            "sku_or_product_name": {
                "type": "string",
                "description": "SKU or name of the product in the order",
            },
        },
        "required": ["order_identifier", "sku_or_product_name"],
    },
)
async def compare_purchased_item_price(
    order_identifier: str,
    sku_or_product_name: str,
) -> dict[str, Any]:
    order = await fetch_order_by_identifier(order_identifier)
    item = _match_order_item(order, sku_or_product_name)
    sku = item["sku"]

    product = await base_tool.http_client.get(
        f"{settings.PRODUCT_SERVICE_URL}/api/v1/products/sku/{sku}"
    )

    purchased_price = float(item.get("unitPrice", 0))
    current_price = float(product.get("basePrice", 0))
    difference = round(current_price - purchased_price, 2)
    pct_change = round((difference / purchased_price) * 100, 2) if purchased_price > 0 else 0.0

    return {
        "orderNumber": order.get("orderNumber", order.get("id")),
        "purchasedAt": order.get("createdAt"),
        "sku": sku,
        "productName": product.get("name") or item.get("productName"),
        "purchasedPrice": purchased_price,
        "currentCatalogPrice": current_price,
        "priceDifference": difference,
        "percentageChange": pct_change,
        "currency": product.get("currency") or order.get("currency", "TRY"),
        "trend": "INCREASED" if difference > 0 else ("DECREASED" if difference < 0 else "UNCHANGED"),
    }


@tool_registry.register(
    name="evaluate_price_match_refund",
    description=(
        "Scenario B.2: Evaluates the 48-hour Price Match Guarantee policy. If a product's price dropped "
        "within 48 hours of purchase, triggers an automatic wallet/card refund for the price difference."
    ),
    parameters={
        "type": "object",
        "properties": {
            "order_identifier": {
                "type": "string",
                "description": "Order number (ORD-xxxx) or order UUID",
            },
            "sku_or_product_name": {
                "type": "string",
                "description": "SKU or product name to evaluate for price protection",
            },
        },
        "required": ["order_identifier", "sku_or_product_name"],
    },
)
async def evaluate_price_match_refund(
    order_identifier: str,
    sku_or_product_name: str,
) -> dict[str, Any]:
    order = await fetch_order_by_identifier(order_identifier)
    item = _match_order_item(order, sku_or_product_name)
    sku = item["sku"]
    quantity = int(item.get("quantity", 1))

    product = await base_tool.http_client.get(
        f"{settings.PRODUCT_SERVICE_URL}/api/v1/products/sku/{sku}"
    )

    purchased_price = float(item.get("unitPrice", 0))
    current_price = float(product.get("basePrice", 0))
    created_at = _parse_iso_datetime(order.get("createdAt"))
    now = datetime.now(UTC)
    hours_elapsed = round(max(0.0, (now - created_at).total_seconds() / 3600.0), 2)

    if current_price >= purchased_price:
        return {
            "eligible": False,
            "reason": "NO_PRICE_DROP",
            "purchasedPrice": purchased_price,
            "currentPrice": current_price,
            "hoursElapsed": hours_elapsed,
            "refundAmount": 0.0,
            "message": "Ürünün güncel fiyatı satın aldığınız fiyattan daha düşük olmadığı için fiyat farkı iadesi uygulanamamaktadır.",
        }

    if hours_elapsed > PRICE_MATCH_WINDOW_HOURS:
        return {
            "eligible": False,
            "reason": "WINDOW_EXPIRED_48H",
            "purchasedPrice": purchased_price,
            "currentPrice": current_price,
            "hoursElapsed": hours_elapsed,
            "policyWindowHours": PRICE_MATCH_WINDOW_HOURS,
            "refundAmount": 0.0,
            "message": (
                f"Fiyat koruma garantimiz satın alma işleminden sonraki 48 saat için geçerlidir "
                f"(Sipariş üzerinden {hours_elapsed:.1f} saat geçmiş)."
            ),
        }

    refund_amount = round((purchased_price - current_price) * quantity, 2)
    currency = order.get("currency", "TRY")
    return {
        "eligible": True,
        "orderNumber": order.get("orderNumber", order.get("id")),
        "sku": sku,
        "productName": product.get("name") or item.get("productName"),
        "purchasedPrice": purchased_price,
        "currentPrice": current_price,
        "quantity": quantity,
        "hoursElapsed": hours_elapsed,
        "refundAmount": refund_amount,
        "currency": currency,
        "refundDestination": "WALLET_AND_CARD",
        "message": (
            f"Fiyat koruma garantimiz kapsamında, satın alma işleminiz üzerinden henüz 48 saat geçmediği için "
            f"({hours_elapsed:.1f} saat) aradaki {refund_amount:.2f} {currency} fark doğrudan cüzdanınıza iade edildi!"
        ),
    }


@tool_registry.register(
    name="optimize_cart_coupons",
    description=(
        "Scenario B.3: Analyzes cart items and categories to calculate the best coupon/campaign "
        "that yields the maximum monetary discount for the customer."
    ),
    parameters={
        "type": "object",
        "properties": {
            "cart_items": {
                "type": "array",
                "description": "List of items in the customer's shopping cart",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "category": {"type": "string"},
                        "price": {"type": "number"},
                        "quantity": {"type": "integer"},
                    },
                    "required": ["name", "price"],
                },
            }
        },
        "required": ["cart_items"],
    },
)
async def optimize_cart_coupons(cart_items: list[dict[str, Any]]) -> dict[str, Any]:
    if not cart_items:
        raise BusinessRuleException("Cart items cannot be empty for coupon optimization")

    total_cart = 0.0
    category_totals: dict[str, float] = {}

    for item in cart_items:
        qty = int(item.get("quantity", 1))
        line_total = float(item.get("price", 0.0)) * qty
        total_cart += line_total
        cat = str(item.get("category", "genel")).strip().lower()
        category_totals[cat] = category_totals.get(cat, 0.0) + line_total

    evaluated: list[dict[str, Any]] = []
    for camp in ACTIVE_CAMPAIGNS:
        discount = 0.0
        if camp["type"] == "CATEGORY_PERCENT":
            cat_spend = category_totals.get(camp["category"], 0.0)
            if cat_spend >= camp["min_spend"]:
                discount = cat_spend * (camp["percent"] / 100.0)
                if "max_discount" in camp:
                    discount = min(discount, float(camp["max_discount"]))
        elif camp["type"] == "CART_FLAT":
            if total_cart >= camp["min_spend"]:
                discount = float(camp["flat_discount"])

        discount = round(discount, 2)
        if discount > 0:
            evaluated.append(
                {
                    "couponCode": camp["code"],
                    "title": camp["title"],
                    "discountAmount": discount,
                    "finalCartTotal": round(total_cart - discount, 2),
                }
            )

    evaluated.sort(key=lambda x: x["discountAmount"], reverse=True)
    best = evaluated[0] if evaluated else None

    return {
        "originalCartTotal": round(total_cart, 2),
        "bestCoupon": best,
        "allApplicableCoupons": evaluated,
        "autoApplied": best is not None,
    }
