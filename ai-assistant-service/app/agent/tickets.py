"""Support ticket event publisher abstractions and Kafka integration.

Emits support.ticket.created domain events adhering to the Unified Event Envelope.
Supports both zero-dependency LoggingTicketPublisher and distributed KafkaTicketPublisher.
"""

from datetime import datetime, timezone
import json
import logging
from typing import Any, Protocol
import uuid

from app.core.config import settings
from app.core.pii import mask_pii

logger = logging.getLogger(__name__)


def build_ticket_event(
    ticket_id: str,
    customer_id: str,
    subject: str,
    summary: str,
    order_number: str | None = None,
    correlation_id: str | None = None,
) -> dict[str, Any]:
    """Construct an immutable domain event conforming to the Unified Event Envelope."""
    # Güvenlik: Yayın öncesi serbest metin alanlarını tekrar PII filtresinden geçir
    clean_subject, _ = mask_pii(subject.strip())
    clean_summary, _ = mask_pii(summary.strip())

    return {
        "eventId": str(uuid.uuid4()),
        "eventType": "support.ticket.created",
        "aggregateId": ticket_id,
        "aggregateType": "SupportTicket",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "version": 1,
        "correlationId": correlation_id,
        "causationId": None,
        "payload": {
            "ticketId": ticket_id,
            "customerId": customer_id,
            "subject": clean_subject,
            "summary": clean_summary,
            "orderNumber": order_number,
            "channel": "ai-assistant",
        },
    }


class TicketPublisher(Protocol):
    """Protocol for publishing support ticket domain events."""

    async def publish(self, event: dict[str, Any]) -> None:
        """Publish the domain event to downstream brokers or logs."""
        ...


class LoggingTicketPublisher:
    """Zero-dependency ticket publisher for local development and testing."""

    async def publish(self, event: dict[str, Any]) -> None:
        payload = event.get("payload", {})
        # PII hijyeni: Serbest metin özeti loglanmaz; yalnızca kimlikler ve başlık kaydedilir
        logger.info(
            "Support ticket created (log publisher): ticket_id=%s, customer_id=%s, order_no=%s, correlation_id=%s",
            event.get("aggregateId"),
            payload.get("customerId"),
            payload.get("orderNumber"),
            event.get("correlationId"),
        )


class KafkaTicketPublisher:
    """Asynchronous Kafka publisher utilizing aiokafka without local outbox table."""

    def __init__(
        self,
        bootstrap_servers: str | None = None,
        topic: str | None = None,
    ) -> None:
        self._servers = bootstrap_servers or settings.KAFKA_BOOTSTRAP_SERVERS
        self._topic = topic or settings.SUPPORT_TICKET_TOPIC
        self._producer = None

    async def start(self) -> None:
        """Initialize the underlying AIOKafkaProducer."""
        try:
            from aiokafka import AIOKafkaProducer
        except ImportError as exc:
            raise RuntimeError(
                "KafkaTicketPublisher requires the 'aiokafka' package. "
                "Install with 'uv add aiokafka' or use TICKET_PUBLISHER=log."
            ) from exc

        self._producer = AIOKafkaProducer(bootstrap_servers=self._servers)
        await self._producer.start()

    async def stop(self) -> None:
        """Gracefully close Kafka producer connections."""
        if self._producer is not None:
            await self._producer.stop()
            self._producer = None

    async def publish(self, event: dict[str, Any]) -> None:
        """Publish support ticket event using aggregateId as the partitioning key."""
        if self._producer is None:
            await self.start()

        key = str(event.get("aggregateId", "")).encode("utf-8")
        value = json.dumps(event, ensure_ascii=False).encode("utf-8")
        assert self._producer is not None
        await self._producer.send_and_wait(self._topic, key=key, value=value)
