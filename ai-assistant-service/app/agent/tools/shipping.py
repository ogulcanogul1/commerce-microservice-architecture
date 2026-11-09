"""Shipment tracking tool with order ownership verification."""

from pydantic import BaseModel, ConfigDict, Field

from app.agent.tools.base import Tool, ToolContext, ToolResult
from app.clients.order import OrderClient
from app.clients.shipping import ShippingClient

SHIPMENT_STATUS_EXPLANATIONS: dict[str, str] = {
    "PENDING": "Kargo kaydı oluşturuluyor.",
    "CREATED": "Kargo kaydı oluşturuldu, kargo firmasına teslim edilmesi bekleniyor.",
    "IN_TRANSIT": "Kargo yolda, transfer merkezleri arasında taşınıyor.",
    "DELIVERED": "Kargo başarıyla alıcıya teslim edildi.",
    "CANCELLED": "Kargo gönderimi iptal edildi.",
}


class GetShipmentArgs(BaseModel):
    """Arguments for querying shipment details by order number."""

    model_config = ConfigDict(extra="forbid")

    order_number: str = Field(
        description="Kargosu sorgulanacak sipariş numarası (örn: ORD-12345)"
    )


class GetShipmentTool(Tool):
    """Queries parcel shipment status by verifying order ownership first."""

    name = "get_shipment"
    description = (
        "Sipariş numarasına ait kargo teslimat durumunu, kargo firmasını, takip numarasını "
        "ve son hareketlerini sorgular."
    )
    args_model = GetShipmentArgs

    def __init__(
        self,
        order_client: OrderClient,
        shipping_client: ShippingClient,
    ) -> None:
        self._order_client = order_client
        self._shipping_client = shipping_client

    async def run(self, args: BaseModel, ctx: ToolContext) -> ToolResult:
        assert isinstance(args, GetShipmentArgs)

        # 1. Aşama: İki Aşamalı Sahiplik Doğrulaması (Kritik Güvenlik Bariyeri):
        # 'shipping-service' veritabanında 'customerId' alanı yer almaz. Dolayısıyla kargo servisi
        # tek başına sahiplik kontrolü yapamaz. IDOR açığını önlemek için Python katmanı ÖNCE 'order-service'
        # üzerinden siparişin bu kullanıcıya ait olduğunu doğrular. Başkasına aitse 'ownership_mismatch'
        # ile reddeder ve kargo servisine asla istek atmaz.
        order = await self._order_client.get_order_by_number(
            order_number=args.order_number,
            user_id=ctx.user_id,
            correlation_id=ctx.correlation_id,
        )

        if order.customer_id.lower() != ctx.user_id.lower():
            return ToolResult(ok=False, error="Sipariş bulunamadı.", reason="ownership_mismatch")

        # 2. Aşama: Sipariş ID'si üzerinden kargo bilgisini çek
        shipment = await self._shipping_client.get_shipment_by_order(
            order_id=order.id,
            user_id=ctx.user_id,
            correlation_id=ctx.correlation_id,
        )

        if shipment is None:
            return ToolResult(
                ok=True,
                data={
                    "order_number": order.order_number,
                    "shipment": None,
                    "mesaj": "Bu sipariş için henüz kargo kaydı yok.",
                },
            )

        status_aciklama = SHIPMENT_STATUS_EXPLANATIONS.get(
            shipment.status,
            f"{shipment.status} (Durum ayrıntısı bilinmiyor.)",
        )

        # Son 3 kargo hareketini al
        last_events = [
            {
                "status": evt.status,
                "description": evt.description,
                "location": evt.location,
                "occurred_at": evt.occurred_at.isoformat(),
            }
            for evt in shipment.events[-3:]
        ]

        data = {
            "order_number": order.order_number,
            "carrier": shipment.carrier,
            "tracking_number": shipment.tracking_number,
            "status": shipment.status,
            "status_aciklama": status_aciklama,
            "estimated_delivery": (
                shipment.estimated_delivery.isoformat()
                if shipment.estimated_delivery
                else None
            ),
            "actual_delivery": (
                shipment.actual_delivery.isoformat()
                if shipment.actual_delivery
                else None
            ),
            "failure_reason": shipment.failure_reason,
            "last_events": last_events,
        }
        return ToolResult(ok=True, data=data)
