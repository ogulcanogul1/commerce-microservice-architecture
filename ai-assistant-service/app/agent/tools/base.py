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
    """Her araç (tool) çağrısına enjekte edilen doğrulanmış istek bağlamı.
    
    Güvenlik Kuralı:
    Müşteri kimliği (user_id) asla LLM'den veya kullanıcı promptundan alınmaz.
    Gateway'in onayladığı RequestContext üzerinden bu nesneye aktarılır.
    """

    user_id: str
    correlation_id: str | None
    question: str  # Maskelenmiş orijinal kullanıcı sorusu


class ToolResult(BaseModel):
    """Bir aracın (tool) çalışması sonucunda dönen birleşik sonuç zarfı."""

    model_config = ConfigDict(frozen=True)

    ok: bool
    data: dict[str, Any] | list[Any] | None = None
    error: str | None = None
    terminal_reply: AgentReply | None = None
    pending_action: PendingAction | None = None

    # İç Sınıflandırma ve Audit Kodu:
    # GÜVENLİK İLKESİ: Modele ve müşteriye sadece nötr jenerik hata döner ("Sipariş bulunamadı").
    # Bu 'reason' alanı ise olayın bir sahiplik uyuşmazlığı ('ownership_mismatch'), yetkisiz erişim ('denied')
    # veya gerçek bir 404 ('not_found') olduğunu belirterek yalnızca Audit mekanizmasına ve Enumeration alarmına bildirir.
    # Bu alan KESİNLİKLE LLM promptuna veya istemci yanıtına yansıtılmaz.
    reason: str | None = None


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
