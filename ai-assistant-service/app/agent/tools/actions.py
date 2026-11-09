"""Proposal tools for sensitive write actions (order cancellation, support tickets).

These tools NEVER execute modifications directly; they only formulate a PendingAction
and register it in the action store for explicit human-in-the-loop confirmation.
"""

import asyncio
from datetime import datetime, timedelta, timezone
import secrets
from pydantic import BaseModel, ConfigDict, Field

from app.agent.models import PendingAction
from app.agent.pending import PendingActionStore
from app.agent.tools.base import Tool, ToolContext, ToolResult
from app.clients.order import OrderClient
from app.core.config import settings
from app.core.pii import mask_pii


class RequestOrderCancellationArgs(BaseModel):
    """Arguments for proposing an order cancellation."""

    model_config = ConfigDict(extra="forbid")

    order_number: str = Field(
        description="İptal edilmek istenen sipariş numarası (örn: ORD-12345)"
    )
    reason: str = Field(
        min_length=1,
        max_length=200,
        description="Siparişin iptal edilme gerekçesi",
    )


class RequestOrderCancellationTool(Tool):
    """Proposes an order cancellation to the customer for explicit confirmation."""

    name = "request_order_cancellation"
    description = (
        "Müşterinin bir siparişi iptal etme talebini alır ve onaylatmak üzere "
        "bekleyen işlem (pending action) oluşturur. Siparişi doğrudan iptal etmez."
    )
    args_model = RequestOrderCancellationArgs

    def __init__(
        self,
        order_client: OrderClient,
        action_store: PendingActionStore,
        ttl_sec: int | None = None,
    ) -> None:
        self._order_client = order_client
        self._action_store = action_store
        self._ttl_sec = ttl_sec if ttl_sec is not None else settings.AGENT_PENDING_TTL_SEC

    async def run(self, args: BaseModel, ctx: ToolContext) -> ToolResult:
        assert isinstance(args, RequestOrderCancellationArgs)

        # 1. Siparişi sorgula ve sahipliğini doğrula
        order = await self._order_client.get_order_by_number(
            order_number=args.order_number,
            user_id=ctx.user_id,
            correlation_id=ctx.correlation_id,
        )

        if order.customer_id.lower() != ctx.user_id.lower():
            return ToolResult(ok=False, error="Sipariş bulunamadı.", reason="ownership_mismatch")

        # Zaten iptal edilmişse aksiyon oluşturma
        if order.status == "CANCELLED":
            return ToolResult(
                ok=True,
                data={
                    "mesaj": "Sipariş zaten iptal edilmiş.",
                    "order_number": order.order_number,
                    "status": order.status,
                },
            )

        # 2. Bekleyen onaylı aksiyon oluştur
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(seconds=self._ttl_sec)
        action_id = secrets.token_urlsafe(24)
        summary = (
            f"{order.order_number} numaralı siparişi iptal etmek istediğinizi "
            f"onaylıyor musunuz? Sebep: {args.reason}"
        )

        action = PendingAction(
            action_id=action_id,
            user_id=ctx.user_id,
            action_type="cancel_order",
            params={
                "order_id": order.id,
                "order_number": order.order_number,
                "reason": args.reason,
            },
            summary=summary,
            created_at=now,
            expires_at=expires_at,
        )
        try:
            stored_action = await asyncio.to_thread(self._action_store.create, action)
        except Exception as exc:
            logger.exception("Failed to store pending cancellation action: %s", exc)
            return ToolResult(
                ok=False,
                error="İşlem onay kaydı oluşturulamadı, lütfen daha sonra tekrar deneyin.",
            )

        return ToolResult(
            ok=True,
            pending_action=stored_action,
            data={
                "mesaj": "Onay bekleniyor",
                "order_number": order.order_number,
                "status": order.status,
                "action_id": stored_action.action_id,
            },
        )


class RequestSupportTicketArgs(BaseModel):
    """Arguments for proposing a customer support ticket."""

    model_config = ConfigDict(extra="forbid")

    subject: str = Field(
        min_length=1,
        max_length=100,
        description="Destek talebinin kısa konusu",
    )
    summary: str = Field(
        min_length=1,
        max_length=500,
        description="Müşteri temsilcisine iletilecek sorun detayı ve özeti",
    )
    order_number: str | None = Field(
        default=None,
        description="Varsa şikayet veya soruyla ilgili sipariş numarası",
    )


class RequestSupportTicketTool(Tool):
    """Proposes creating a human support ticket to the customer for explicit confirmation."""

    name = "request_support_ticket"
    description = (
        "Sorun çözülemediğinde veya yetkili istendiğinde müşteri temsilcisine "
        "destek talebi açmak üzere bekleyen onaylı işlem oluşturur."
    )
    args_model = RequestSupportTicketArgs

    def __init__(
        self,
        order_client: OrderClient,
        action_store: PendingActionStore,
        ttl_sec: int | None = None,
    ) -> None:
        self._order_client = order_client
        self._action_store = action_store
        self._ttl_sec = ttl_sec if ttl_sec is not None else settings.AGENT_PENDING_TTL_SEC

    async def run(self, args: BaseModel, ctx: ToolContext) -> ToolResult:
        assert isinstance(args, RequestSupportTicketArgs)

        # Sipariş numarası verilmişse sahipliğini doğrula
        order_no = args.order_number
        if order_no:
            order = await self._order_client.get_order_by_number(
                order_number=order_no,
                user_id=ctx.user_id,
                correlation_id=ctx.correlation_id,
            )
            if order.customer_id.lower() != ctx.user_id.lower():
                return ToolResult(ok=False, error="Sipariş bulunamadı.", reason="ownership_mismatch")

        clean_subject, _ = mask_pii(args.subject.strip())
        clean_summary, _ = mask_pii(args.summary.strip())

        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(seconds=self._ttl_sec)
        action_id = secrets.token_urlsafe(24)
        summary_prompt = (
            f"Bir müşteri temsilcisine destek talebi açmamı onaylıyor musunuz? "
            f"Konu: {clean_subject}"
        )

        action = PendingAction(
            action_id=action_id,
            user_id=ctx.user_id,
            action_type="create_support_ticket",
            params={
                "subject": clean_subject,
                "summary": clean_summary,
                "order_number": order_no,
            },
            summary=summary_prompt,
            created_at=now,
            expires_at=expires_at,
        )
        try:
            stored_action = await asyncio.to_thread(self._action_store.create, action)
        except Exception as exc:
            logger.exception("Failed to store pending support ticket action: %s", exc)
            return ToolResult(
                ok=False,
                error="İşlem onay kaydı oluşturulamadı, lütfen daha sonra tekrar deneyin.",
            )

        return ToolResult(
            ok=True,
            pending_action=stored_action,
            data={
                "mesaj": "Onay bekleniyor",
                "subject": clean_subject,
                "action_id": stored_action.action_id,
            },
        )
