import logging
from typing import Any

from aiokafka import AIOKafkaProducer

from app.core.config import settings
from app.messaging.event_envelope import EventEnvelope
from app.tools.support_tools import set_escalation_publisher

logger = logging.getLogger(__name__)


class KafkaEscalationProducer:
    """
    Asynchronous Kafka producer (`aiokafka`) publishing urgent AI support escalations
    to topic `support.ticket.created` wrapped in the platform Unified Event Envelope.
    """

    def __init__(self, producer: AIOKafkaProducer | None = None) -> None:
        self._producer = producer
        self._started = False
        self.published_history: list[EventEnvelope] = []

    async def start(self) -> None:
        set_escalation_publisher(self.publish_support_ticket)

        if not settings.KAFKA_ENABLED:
            logger.info("Kafka producer is disabled via configuration (KAFKA_ENABLED=false).")
            return

        try:
            if self._producer is None:
                self._producer = AIOKafkaProducer(
                    bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
                )
            await self._producer.start()
            self._started = True
            logger.info(
                "KafkaEscalationProducer connected to %s (topic: %s)",
                settings.KAFKA_BOOTSTRAP_SERVERS,
                settings.KAFKA_SUPPORT_TOPIC,
            )
        except Exception as exc:
            logger.error("Failed to start KafkaEscalationProducer: %s", exc)
            self._started = False

    async def stop(self) -> None:
        if self._producer is not None and self._started:
            try:
                await self._producer.stop()
                logger.info("KafkaEscalationProducer stopped cleanly.")
            except Exception as exc:
                logger.warning("Error while stopping KafkaEscalationProducer: %s", exc)
            finally:
                self._started = False

    async def publish_support_ticket(self, ticket_payload: dict[str, Any]) -> EventEnvelope:
        envelope = EventEnvelope.create_support_ticket_event(ticket_payload)
        self.published_history.append(envelope)

        if self._producer is not None and (self._started or not settings.KAFKA_ENABLED):
            try:
                key_bytes = envelope.aggregateId.encode("utf-8")
                value_bytes = envelope.model_dump_json().encode("utf-8")
                headers = [
                    ("X-Correlation-Id", envelope.correlationId.encode("utf-8")),
                    ("eventType", envelope.eventType.encode("utf-8")),
                ]
                await self._producer.send_and_wait(
                    settings.KAFKA_SUPPORT_TOPIC,
                    value=value_bytes,
                    key=key_bytes,
                    headers=headers,
                )
                logger.info(
                    "Published SupportTicketCreated event %s for ticket %s to topic %s",
                    envelope.eventId,
                    envelope.aggregateId,
                    settings.KAFKA_SUPPORT_TOPIC,
                )
            except Exception as exc:
                logger.error("Failed to send support escalation event to Kafka: %s", exc)

        return envelope


kafka_producer = KafkaEscalationProducer()
