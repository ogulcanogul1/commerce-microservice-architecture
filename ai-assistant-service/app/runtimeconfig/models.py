from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.core.config import Settings


class AgentRuntime(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    max_steps: int = Field(ge=1, le=10, description="Döngü adım sınırı")
    llm_timeout_sec: float = Field(gt=0, description="Tekil LLM çağrı timeout (sn)")
    # Tavan: Gateway aiChatCircuitBreaker TimeLimiter 70 sn. Yükseltmek Gateway'i de değiştirmeyi gerektirir.
    turn_timeout_sec: float = Field(gt=0, le=65.0, description="Toplam tur timeout (sn)")
    max_output_tokens: int = Field(ge=50, le=4000, description="Adım başına maksimum token")
    temperature: float = Field(ge=0.0, le=1.0, description="LLM sıcaklık değeri")

    @model_validator(mode="after")
    def _llm_call_fits_turn(self) -> "AgentRuntime":
        if self.llm_timeout_sec > self.turn_timeout_sec:
            raise ValueError("agent.llm_timeout_sec, agent.turn_timeout_sec değerinden büyük olamaz")
        return self


class RagRuntime(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    # Tavan: Gateway aiRagAnswerCircuitBreaker TimeLimiter 55 sn.
    turn_timeout_sec: float = Field(gt=0, le=50.0, description="RAG toplam cevaplama turu timeout (sn)")
    top_k: int = Field(ge=1, le=20, description="Getirilecek chunk sayısı")
    max_attempts: int = Field(ge=1, le=3, description="LLM doğrulama tekrar deneme sayısı")
    min_dense_score: float | None = Field(default=None, ge=0.0, le=1.0, description="Cosine eşiği")
    max_output_tokens: int = Field(ge=50, description="Maksimum çıktı token sayısı")
    llm_timeout_sec: float = Field(gt=0, description="Tekil LLM çağrı timeout (sn)")
    temperature: float = Field(ge=0.0, le=1.0, description="LLM sıcaklık değeri")
    context_token_budget: int = Field(ge=100, description="Prompt context bütçesi")

    @field_validator("min_dense_score", mode="before")
    @classmethod
    def _normalize_empty_min_dense_score(cls, v: Any) -> Any:
        # Spring Cloud Config boş YAML değerlerini "" olarak gönderebilir
        if isinstance(v, str) and not v.strip():
            return None
        return v

    @model_validator(mode="after")
    def _llm_call_fits_turn(self) -> "RagRuntime":
        if self.llm_timeout_sec > self.turn_timeout_sec:
            raise ValueError("rag.llm_timeout_sec, rag.turn_timeout_sec değerinden büyük olamaz")
        return self

    def generation_overrides(self) -> dict[str, Any]:
        """GenerationConfig alan adlarıyla override sözlüğü (turn_timeout_sec hariç)."""
        return {
            "top_k": self.top_k,
            "max_attempts": self.max_attempts,
            "min_dense_score": self.min_dense_score,
            "max_output_tokens": self.max_output_tokens,
            "llm_timeout_sec": self.llm_timeout_sec,
            "temperature": self.temperature,
            "context_token_budget": self.context_token_budget,
        }


class BudgetRuntime(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    daily_limit: int = Field(ge=1, description="Günlük kullanıcı token limiti")
    per_minute_limit: int = Field(ge=1, description="Dakikalık kullanıcı token limiti")
    provider_tpm_limit: int = Field(ge=0, description="Ortak dakikalık token kotası (0=kapalı)")
    prompt_overhead: int = Field(ge=0, description="Sistem prompt ve araçlar için token payı")

    @model_validator(mode="after")
    def _minute_fits_daily(self) -> "BudgetRuntime":
        if self.per_minute_limit > self.daily_limit:
            raise ValueError("budget.per_minute_limit, budget.daily_limit değerinden büyük olamaz")
        return self


class LoggingRuntime(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] | None = None

    @field_validator("level", mode="before")
    @classmethod
    def _normalize_log_level(cls, v: Any) -> Any:
        if isinstance(v, str):
            cleaned = v.strip().upper()
            return cleaned if cleaned else None
        return v


# Runtime alan yolu -> Settings alan adı. Öncelik ve 'pinned' hesabı bu tabloya dayanır.
ENV_FIELD_MAP: dict[str, str] = {
    "agent.max_steps": "AGENT_MAX_STEPS",
    "agent.llm_timeout_sec": "AGENT_LLM_TIMEOUT_SEC",
    "agent.turn_timeout_sec": "AGENT_TURN_TIMEOUT_SEC",
    "agent.max_output_tokens": "AGENT_MAX_OUTPUT_TOKENS",
    "agent.temperature": "AGENT_TEMPERATURE",
    "rag.turn_timeout_sec": "RAG_TURN_TIMEOUT_SEC",
    "rag.top_k": "RAG_TOP_K",
    "rag.max_attempts": "RAG_MAX_ATTEMPTS",
    "rag.min_dense_score": "RAG_MIN_DENSE_SCORE",
    "rag.max_output_tokens": "RAG_MAX_OUTPUT_TOKENS",
    "rag.llm_timeout_sec": "RAG_LLM_TIMEOUT_SEC",
    "rag.temperature": "RAG_TEMPERATURE",
    "rag.context_token_budget": "RAG_CONTEXT_TOKEN_BUDGET",
    "budget.daily_limit": "TOKEN_BUDGET_DAILY_LIMIT",
    "budget.per_minute_limit": "TOKEN_BUDGET_PER_MINUTE_LIMIT",
    "budget.provider_tpm_limit": "PROVIDER_TPM_LIMIT",
    "budget.prompt_overhead": "TOKEN_BUDGET_PROMPT_OVERHEAD",
}


def pinned_paths(s: Settings) -> frozenset[str]:
    """Çevre değişkeni (.env veya OS env) ile açıkça ezilmiş runtime yollarını döndürür."""
    return frozenset(
        path for path, env_field in ENV_FIELD_MAP.items() if env_field in s.model_fields_set
    )


class RuntimeSettings(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    agent: AgentRuntime
    rag: RagRuntime
    budget: BudgetRuntime
    logging: LoggingRuntime = Field(default_factory=LoggingRuntime)

    @classmethod
    def from_startup(cls, s: Settings) -> "RuntimeSettings":
        """Mevcut Settings nesnesinden başlangıç baseline RuntimeSettings üretir."""
        from app.runtimeconfig.paths import set_path

        tree: dict[str, Any] = {}
        for path, env_field in ENV_FIELD_MAP.items():
            set_path(tree, path, getattr(s, env_field))
        tree["logging"] = {}
        return cls.model_validate(tree)
