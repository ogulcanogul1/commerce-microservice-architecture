"""Order query tools for getting specific orders and listing customer orders."""

from pydantic import BaseModel, ConfigDict, Field

from app.agent.tools.base import Tool, ToolContext, ToolResult
from app.clients.order import OrderClient

ORDER_STATUS_EXPLANATIONS: dict[str, str] = {
    "PENDING": "Sipariş oluşturuldu, stok ve ödeme onayı bekleniyor.",
    "INVENTORY_RESERVED": "Sipariş ürünleri depoda rezerve edildi, ödeme bekleniyor.",
    "PAYMENT_AUTHORIZED": "Ödeme ön onayı alındı, sipariş hazırlanıyor.",
    "SHIPPING_CREATED": "Kargo kaydı oluşturuldu, kargo firmasına teslim edilmesi bekleniyor.",
    "CONFIRMED": "Sipariş başarıyla onaylandı ve tamamlandı.",
    "INVENTORY_FAILED": "Yetersiz stok nedeniyle sipariş tamamlanamadı.",
    "PAYMENT_FAILED": "Ödeme alınamadığı için sipariş tamamlanamadı.",
    "SHIPPING_FAILED": "Kargo sürecinde hata oluştuğu için sipariş tamamlanamadı.",
    "CANCELLED": "Sipariş iptal edildi.",
}


class GetOrderArgs(BaseModel):
    """Arguments for fetching a specific customer order."""

    model_config = ConfigDict(extra="forbid")

    order_number: str = Field(
        description="Sorgulanacak sipariş numarası (örn: ORD-12345)"
    )


class GetOrderTool(Tool):
    """Fetches details, status, and items for a specific order owned by the customer."""

    name = "get_order"
    description = "Belirtilen sipariş numarasına göre sipariş detaylarını, durumunu ve içerdiği ürünleri getirir."
    args_model = GetOrderArgs

    def __init__(self, order_client: OrderClient) -> None:
        self._order_client = order_client

    async def run(self, args: BaseModel, ctx: ToolContext) -> ToolResult:
        assert isinstance(args, GetOrderArgs)
        order = await self._order_client.get_order_by_number(
            order_number=args.order_number,
            user_id=ctx.user_id,
            correlation_id=ctx.correlation_id,
        )

        # Savunma derinliği: downstream hatalı kayıt dönerse bile müşteri kimliğini doğrula
        if order.customer_id.lower() != ctx.user_id.lower():
            return ToolResult(ok=False, error="Sipariş bulunamadı.")

        status_aciklama = ORDER_STATUS_EXPLANATIONS.get(
            order.status,
            f"{order.status} (Durum ayrıntısı bilinmiyor.)",
        )

        data = {
            "order_number": order.order_number,
            "status": order.status,
            "status_aciklama": status_aciklama,
            "total_amount": float(order.total_amount),
            "currency": order.currency,
            "item_count": len(order.items),
            "items": [
                {
                    "product_name": item.product_name,
                    "quantity": item.quantity,
                }
                for item in order.items
            ],
            "failure_reason": order.failure_reason,
            "created_at": order.created_at.isoformat(),
            "updated_at": order.updated_at.isoformat(),
        }
        return ToolResult(ok=True, data=data)


class ListMyOrdersArgs(BaseModel):
    """Arguments for listing customer orders."""

    model_config = ConfigDict(extra="forbid")

    limit: int = Field(
        default=5,
        ge=1,
        le=10,
        description="Listelenecek maksimum sipariş sayısı (1-10 arası, varsayılan 5)",
    )


class ListMyOrdersTool(Tool):
    """Lists recent orders placed by the authenticated customer."""

    name = "list_my_orders"
    description = "Giriş yapmış müşterinin kendi son siparişlerini listeler."
    args_model = ListMyOrdersArgs

    def __init__(self, order_client: OrderClient) -> None:
        self._order_client = order_client

    async def run(self, args: BaseModel, ctx: ToolContext) -> ToolResult:
        assert isinstance(args, ListMyOrdersArgs)
        page = await self._order_client.list_orders(
            customer_id=ctx.user_id,
            user_id=ctx.user_id,
            correlation_id=ctx.correlation_id,
            size=args.limit,
        )

        # Başka müşteriye ait kayıt gelirse ayıkla
        verified_items = [
            order for order in page.items
            if order.customer_id.lower() == ctx.user_id.lower()
        ]

        formatted_orders = [
            {
                "order_number": o.order_number,
                "status": o.status,
                "status_aciklama": ORDER_STATUS_EXPLANATIONS.get(
                    o.status,
                    f"{o.status} (Durum ayrıntısı bilinmiyor.)",
                ),
                "total_amount": float(o.total_amount),
                "currency": o.currency,
                "created_at": o.created_at.isoformat(),
            }
            for o in verified_items
        ]

        return ToolResult(
            ok=True,
            data={
                "total": len(verified_items),
                "orders": formatted_orders,
            },
        )
