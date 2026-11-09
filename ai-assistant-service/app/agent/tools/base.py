"""Base abstractions for agentic tools.

Enforces strict parameter schemas with extra="forbid" (preventing caller identity injection),
provides clean JSON schemas without title metadata, and encapsulates tool results.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any
from pydantic import BaseModel, ConfigDict

from app.agent.models import AgentReply, PendingAction
from app.llm.base import ToolDefinition


@dataclass(frozen=True)
class ToolContext:
    """Execution context injected into every tool invocation from verified request headers."""

    user_id: str
    correlation_id: str | None
    question: str  # Masked original user question


class ToolResult(BaseModel):
    """Unified outcome of a tool execution."""

    model_config = ConfigDict(frozen=True)

    ok: bool
    data: dict[str, Any] | list[Any] | None = None
    error: str | None = None
    terminal_reply: AgentReply | None = None
    pending_action: PendingAction | None = None
    reason: str | None = None  # İç sonuç kodu (audit için). ASLA modele/müşteriye gösterilmez


class Tool(ABC):
    """Abstract base class for all agentic tools."""

    name: str
    description: str
    args_model: type[BaseModel]

    def definition(self) -> ToolDefinition:
        """Generate provider-friendly JSON Schema without redundant 'title' tags."""
        schema = self.args_model.model_json_schema()
        schema.pop("title", None)
        if "properties" in schema:
            for prop in schema["properties"].values():
                if isinstance(prop, dict):
                    prop.pop("title", None)
        schema["additionalProperties"] = False
        return ToolDefinition(
            name=self.name,
            description=self.description,
            parameters=schema,
        )

    @abstractmethod
    async def run(self, args: BaseModel, ctx: ToolContext) -> ToolResult:
        """Execute the tool logic using validated args and security context."""
        pass
