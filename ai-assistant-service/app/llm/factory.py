from app.core.config import settings
from app.core.exceptions import BusinessRuleException
from app.core.security import get_request_context
from app.llm.base import BaseLLMProvider
from app.llm.providers.claude_provider import ClaudeProvider
from app.llm.providers.gemini_provider import GeminiProvider
from app.llm.providers.local_provider import LocalProvider
from app.llm.providers.openai_provider import OpenAIProvider

SUPPORTED_PROVIDERS = ("claude", "openai", "gemini", "local", "ollama")


class LLMFactory:
    """
    Strategy Factory that resolves the active LLM provider per request or environment default.
    Priority:
      1. Explicit `provider_name` argument
      2. Request header `X-Model-Provider` (stored in RequestContext)
      3. `settings.DEFAULT_LLM_PROVIDER` environment variable
    """

    @staticmethod
    def get_provider(provider_name: str | None = None) -> BaseLLMProvider:
        ctx_provider = get_request_context().model_provider
        target = (provider_name or ctx_provider or settings.DEFAULT_LLM_PROVIDER).strip().lower()

        match target:
            case "claude" | "anthropic":
                return ClaudeProvider()
            case "openai" | "gpt":
                return OpenAIProvider()
            case "gemini" | "google":
                return GeminiProvider()
            case "local" | "ollama" | "vllm":
                return LocalProvider()
            case _:
                raise BusinessRuleException(
                    detail=(
                        f"Unsupported LLM provider '{target}'. "
                        f"Supported providers are: {', '.join(SUPPORTED_PROVIDERS)}"
                    ),
                    title="Invalid Model Provider",
                    error_type="https://api.commerce.com/errors/unsupported-llm-provider",
                )
