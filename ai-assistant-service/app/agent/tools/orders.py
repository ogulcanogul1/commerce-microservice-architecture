"""Order query tools for getting specific orders and listing customer orders."""

import logging
from pydantic import BaseModel, ConfigDict, Field

from app.agent.tools.base import Tool, ToolContext, ToolResult
from app.clients.order import OrderClient
from app.core.audit import write_audit

logger = logging.getLogger(__name__)

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

        # Savunma Derinliği (Defense-in-Depth):
        # Downstream mikroservis (order-service) sahiplik doğrulaması yapsa bile,
        # Python ajan katmanı dönen kaydın gerçekten bu kullanıcıya ait olduğunu ikinci kez teyit eder.
        # Eğer bir uyuşmazlık varsa saldırgana siparişin varlığını ifşa etmemek için "Sipariş bulunamadı" denir,
        # fakat iç denetim izine 'ownership_mismatch' kodu yazılarak enumeration alarmı beslenir.
        if order.customer_id.lower() != ctx.user_id.lower():
            return ToolResult(ok=False, error="Sipariş bulunamadı.", reason="ownership_mismatch")

        status_aciklama = ORDER_STATUS_EXPLANATIONS.get(
            order.status,
            f"{order.status} (Durum ayrıntısı bilinmiyor.)",
        )

        data = {
            "order_number": order.order_number,
            "status": order.status,
            "status_aciklama": status_aciklama,
            "total_amount": f"{order.total_amount:.2f}",
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
        if len(verified_items) != len(page.items):
            logger.error("Downstream başka müşteriye ait kayıt döndürdü (ownership isolation ihlali)")
            write_audit(
                "downstream_isolation_violation",
                user_id=ctx.user_id,
                correlation_id=ctx.correlation_id,
                outcome="isolation_violation",
                total_received=len(page.items),
                verified=len(verified_items),
            )

        formatted_orders = [
            {
                "order_number": o.order_number,
                "status": o.status,
                "status_aciklama": ORDER_STATUS_EXPLANATIONS.get(
                    o.status,
                    f"{o.status} (Durum ayrıntısı bilinmiyor.)",
                ),
                "total_amount": f"{o.total_amount:.2f}",
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
