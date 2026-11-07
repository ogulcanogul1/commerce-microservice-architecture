"""Domain models for agentic reasoning, replies, and pending actions."""

from datetime import datetime
from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field

from app.api.answer import CitationResponse
from app.llm.base import TokenUsage

ActionType = Literal["cancel_order", "create_support_ticket"]
ReplyKind = Literal["answer", "policy_answer", "abstained", "pending_action", "fallback"]


class PendingAction(BaseModel):
    """An action proposed by the agent that requires explicit user confirmation before execution."""

    model_config = ConfigDict(frozen=True)

    action_id: str
    user_id: str
    action_type: ActionType
    params: dict[str, Any]
    summary: str
    created_at: datetime
    expires_at: datetime


class AgentReply(BaseModel):
    """Normalized response returned by the AgentService."""

    model_config = ConfigDict(frozen=True)

    kind: ReplyKind
    reply: str
    citations: list[CitationResponse] = Field(default_factory=list)
    pending_action: PendingAction | None = None
    steps: int = 1
    usage: TokenUsage | None = None
