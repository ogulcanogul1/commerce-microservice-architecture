import uuid
from collections.abc import Awaitable, Callable
from typing import Any

from app.core.security import get_request_context, require_authenticated_user
from app.tools.base_tool import tool_registry

EscalationPublisher = Callable[[dict[str, Any]], Awaitable[None]]

_escalation_publisher: EscalationPublisher | None = None


def set_escalation_publisher(publisher: EscalationPublisher | None) -> None:
    """Registers the async Kafka escalation publisher (wired in Aşama 5)."""
    global _escalation_publisher
    _escalation_publisher = publisher


@tool_registry.register(
    name="escalate_to_human_support",
    description=(
        "Scenario E.1: Detects customer frustration/anger or explicit request for a human agent "
        "and publishes an urgent support ticket event to Kafka topic 'support.ticket.created'."
    ),
    parameters={
        "type": "object",
        "properties": {
            "reason": {
                "type": "string",
                "description": "Escalation reason code (e.g. CUSTOMER_FRUSTRATION_AND_DELAYED_SHIPMENT)",
            },
            "chat_summary": {
                "type": "string",
                "description": "Concise summary of the customer's issue and conversation context",
            },
            "order_id": {
                "type": "string",
                "description": "Related order number or UUID if applicable",
            },
            "urgency": {
                "type": "string",
                "description": "Urgency level: CRITICAL, HIGH, or MEDIUM",
            },
            "suggested_action": {
                "type": "string",
                "description": "Recommended action for the senior support specialist (e.g. apology coupon)",
            },
        },
        "required": ["reason", "chat_summary"],
    },
)
async def escalate_to_human_support(
    reason: str,
    chat_summary: str,
    order_id: str | None = None,
    urgency: str = "CRITICAL",
    suggested_action: str = "Müşteriye 100 TL özür kuponu tanımlanarak öncelikli aranması önerilir.",
) -> dict[str, Any]:
    ctx = require_authenticated_user()
    ticket_id = f"SUP-{uuid.uuid4().int % 9000 + 1000}"

    ticket_payload: dict[str, Any] = {
        "ticketId": ticket_id,
        "customerId": ctx.user_id,
        "customerEmail": ctx.user_email,
        "urgency": urgency.upper(),
        "reason": reason,
        "orderId": order_id,
        "chatSummary": chat_summary,
        "suggestedAction": suggested_action,
        "correlationId": get_request_context().correlation_id,
    }

    if _escalation_publisher is not None:
        await _escalation_publisher(ticket_payload)

    return {
        "escalated": True,
        "ticketId": ticket_id,
        "urgency": urgency.upper(),
        "estimatedWaitMinutes": 2,
        "payload": ticket_payload,
        "message": (
            f"Yaşadığınız gecikme ve aksaklık için çok üzgünüz. Talebinizi en yüksek öncelikle "
            f"kıdemli destek uzmanımıza aktardım (Bilet No: #{ticket_id}). "
            "Bir temsilcimiz 2 dakika içerisinde bu ekran üzerinden görüşmeye dahil olacaktır."
        ),
    }
