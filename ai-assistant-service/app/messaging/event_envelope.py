import uuid
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field

from app.core.security import get_request_context


def _utc_iso_now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _new_uuid_str() -> str:
    return str(uuid.uuid4())


class EventEnvelope(BaseModel):
    """
    Standardized Commerce Platform Unified Event Envelope (AGENTS.md Rule 3).
    All Kafka messages across Java and Python services must conform to this schema.
    """

    eventId: str = Field(default_factory=_new_uuid_str)
    eventType: str
    aggregateId: str
    aggregateType: str
    timestamp: str = Field(default_factory=_utc_iso_now)
    version: int = 1
    correlationId: str = Field(default_factory=_new_uuid_str)
    causationId: str = Field(default_factory=_new_uuid_str)
    payload: dict[str, Any]

    @classmethod
    def create_support_ticket_event(cls, ticket_payload: dict[str, Any]) -> "EventEnvelope":
        ctx = get_request_context()
        corr_id = ticket_payload.get("correlationId") or ctx.correlation_id or _new_uuid_str()
        try:
            # Ensure valid UUIDv4 format for correlationId/causationId
            uuid.UUID(str(corr_id))
            valid_corr_id = str(corr_id)
        except ValueError:
            valid_corr_id = _new_uuid_str()

        event_id = _new_uuid_str()
        return cls(
            eventId=event_id,
            eventType="SupportTicketCreated",
            aggregateId=str(ticket_payload.get("ticketId", "SUP-0000")),
            aggregateType="SupportTicket",
            version=1,
            correlationId=valid_corr_id,
            causationId=event_id,
            payload=ticket_payload,
        )
