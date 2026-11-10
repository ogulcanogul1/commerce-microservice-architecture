"""Action executor executing confirmed pending operations.

Executes confirmed actions independently of the LLM: verifies current order status,
invokes downstream cancellation, and emits support ticket domain events.
"""

import logging
import uuid

from app.agent.models import ExecutionResult, PendingAction
from app.agent.tickets import TicketPublisher, build_ticket_event
from app.clients.base import (
    DownstreamBadRequest,
    DownstreamForbidden,
    DownstreamNotFound,
)
from app.clients.order import OrderClient
from app.core.audit import (
    OUTCOME_DENIED,
    OUTCOME_NOT_FOUND,
    OUTCOME_OWNERSHIP_MISMATCH,
    record_denied_access,
    write_audit,
)
from app.core.security import RequestContext

logger = logging.getLogger(__name__)


class ActionExecutor:
    """Executes validated and user-confirmed operations."""

    def __init__(
        self,
        order_client: OrderClient,
        ticket_publisher: TicketPublisher,
    ) -> None:
        self._order_client = order_client
        self._publisher = ticket_publisher

    async def execute(
        self,
        action: PendingAction,
        ctx: RequestContext,
    ) -> ExecutionResult:
        """Dispatch confirmed action to appropriate backend service."""
        if action.action_type == "cancel_order":
            return await self._execute_cancel_order(action, ctx)

        if action.action_type == "create_support_ticket":
            return await self._execute_create_ticket(action, ctx)

        return ExecutionResult(ok=False, message="Bilinmeyen işlem türü.")

    async def _execute_cancel_order(
        self,
        action: PendingAction,
        ctx: RequestContext,
    ) -> ExecutionResult:
        order_number = action.params.get("order_number", "")
        order_id = action.params.get("order_id", "")
        reason = action.params.get("reason", "Müşteri talebiyle iptal")

        try:
            # 1. Aşama: Durum Tazeleme (State Refresh)
            # Teklifin oluşturulduğu an ile kullanıcının onayladığı an arasında zaman geçmiştir
            # (örn. sipariş kargoya verilmiş veya iptal edilmiş olabilir). Güncel durum veritabanından çekilir.
            current_order = await self._order_client.get_order_by_number(
                order_number=order_number,
                user_id=ctx.user_id,
                correlation_id=ctx.correlation_id,
            )

            # 2. Aşama: Çalıştırma Anı Sahiplik Kontrolü (Execution-Time Ownership Check)
            # Aksiyonu onaylayan kişinin gerçekten siparişin sahibi olup olmadığı son kez teyit edilir.
            # Uyuşmazlık varsa 'ownership_check' denetim kaydı basılır ve enumeration sayacına işlenir.
            if current_order.customer_id.lower() != ctx.user_id.lower():
                write_audit(
                    "ownership_check",
                    user_id=ctx.user_id,
                    correlation_id=ctx.correlation_id,
                    outcome=OUTCOME_OWNERSHIP_MISMATCH,
                    action_type="cancel_order",
                )
                await record_denied_access(ctx.user_id, ctx.correlation_id)
                return ExecutionResult(
                    ok=False,
                    message="Bu sipariş için işlem yapma yetkiniz yok.",
                )

            # Zaten iptal edilmişse gereksiz POST atmadan başarılı dön
            if current_order.status == "CANCELLED":
                return ExecutionResult(
                    ok=True,
                    message="Sipariş zaten iptal edilmiş.",
                )

            await self._order_client.cancel_order(
                order_id=order_id,
                reason=reason,
                user_id=ctx.user_id,
                correlation_id=ctx.correlation_id,
            )
            return ExecutionResult(
                ok=True,
                message="Siparişiniz başarıyla iptal edildi.",
            )
        except DownstreamForbidden:
            logger.warning("Downstream denied access during order cancellation for user %s", ctx.user_id)
            write_audit(
                "ownership_check",
                user_id=ctx.user_id,
                correlation_id=ctx.correlation_id,
                outcome=OUTCOME_DENIED,
                action_type="cancel_order",
                reason="downstream_forbidden",
            )
            await record_denied_access(ctx.user_id, ctx.correlation_id)
            return ExecutionResult(
                ok=False,
                message="Bu sipariş için işlem yapma yetkiniz yok.",
            )
        except DownstreamNotFound:
            logger.warning("Downstream order not found during cancellation for user %s", ctx.user_id)
            write_audit(
                "ownership_check",
                user_id=ctx.user_id,
                correlation_id=ctx.correlation_id,
                outcome=OUTCOME_NOT_FOUND,
                action_type="cancel_order",
                reason="downstream_not_found",
            )
            await record_denied_access(ctx.user_id, ctx.correlation_id)
            return ExecutionResult(
                ok=False,
                message="Sipariş bulunamadı.",
            )
        except DownstreamBadRequest as exc:
            # Ham hata detayı müşteriye doğrudan gösterilmez, loglanır
            logger.warning("Downstream rejected order cancellation: %s", exc.detail)
            return ExecutionResult(
                ok=False,
                message="Bu sipariş mevcut durumunda iptal edilemiyor.",
            )
        except Exception as exc:
            logger.exception("Failed to execute order cancellation: %s", exc)
            return ExecutionResult(
                ok=False,
                message="Sipariş iptali sırasında bir hata oluştu.",
            )

    async def _execute_create_ticket(
        self,
        action: PendingAction,
        ctx: RequestContext,
    ) -> ExecutionResult:
        ticket_id = str(uuid.uuid4())
        subject = action.params.get("subject", "Destek Talebi")
        summary = action.params.get("summary", "")
        order_number = action.params.get("order_number")

        event = build_ticket_event(
            ticket_id=ticket_id,
            customer_id=ctx.user_id,
            subject=subject,
            summary=summary,
            order_number=order_number,
            correlation_id=ctx.correlation_id,
        )

        try:
            await self._publisher.publish(event)
            short_id = ticket_id[:8]
            return ExecutionResult(
                ok=True,
                message=f"Destek talebiniz oluşturuldu. Talep no: {short_id}",
            )
        except Exception as exc:
            logger.exception("Failed to publish support ticket event: %s", exc)
            return ExecutionResult(
                ok=False,
                message="Destek talebi oluşturulurken bir hata oluştu.",
            )
