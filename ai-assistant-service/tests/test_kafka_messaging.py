import json
from unittest.mock import AsyncMock
import uuid
import pytest

from app.core.config import settings
from app.core.security import RequestContext, _request_context_var, set_request_context
from app.messaging.event_envelope import EventEnvelope
from app.messaging.kafka_producer import KafkaEscalationProducer
from app.tools import tool_registry


@pytest.mark.asyncio
async def test_kafka_escalation_producer_publishes_unified_event_envelope():
    mock_aio_producer = AsyncMock()
    producer = KafkaEscalationProducer(producer=mock_aio_producer)
    await producer.start()

    customer_id = "11111111-2222-3333-4444-555555555555"
    corr_id = str(uuid.uuid4())
    token = set_request_context(
        RequestContext(
            correlation_id=corr_id,
            user_id=customer_id,
            user_email="angry.user@example.com",
        )
    )

    try:
        result = await tool_registry.execute(
            "escalate_to_human_support",
            {
                "reason": "CUSTOMER_FRUSTRATION_AND_DELAYED_SHIPMENT",
                "chat_summary": "3 gündür kargo gelmedi, müşteri canlı temsilci istedi.",
                "order_id": "ORD-9912",
                "urgency": "CRITICAL",
            },
        )
        assert result["escalated"] is True
        ticket_id = result["ticketId"]

        assert len(producer.published_history) == 1
        envelope: EventEnvelope = producer.published_history[0]
        assert envelope.eventType == "SupportTicketCreated"
        assert envelope.aggregateId == ticket_id
        assert envelope.aggregateType == "SupportTicket"
        assert envelope.version == 1
        assert envelope.correlationId == corr_id
        assert envelope.payload["customerId"] == customer_id
        assert envelope.payload["orderId"] == "ORD-9912"

        mock_aio_producer.send_and_wait.assert_awaited_once()
        call_args = mock_aio_producer.send_and_wait.call_args
        assert call_args.args[0] == settings.KAFKA_SUPPORT_TOPIC
        assert call_args.kwargs["key"] == ticket_id.encode("utf-8")

        raw_json = json.loads(call_args.kwargs["value"].decode("utf-8"))
        assert set(raw_json.keys()) == {
            "eventId",
            "eventType",
            "aggregateId",
            "aggregateType",
            "timestamp",
            "version",
            "correlationId",
            "causationId",
            "payload",
        }
    finally:
        _request_context_var.reset(token)
        await producer.stop()
