from openai import AsyncOpenAI

from app.core.config import settings
from app.llm.providers.openai_provider import OpenAIProvider


class LocalProvider(OpenAIProvider):
    """
    Local open-source LLM provider (Ollama / vLLM: Llama 3.2, DeepSeek-R1, Qwen)
    using OpenAI-compatible HTTP API.
    """

    provider_name = "local"

    def __init__(
        self,
        base_url: str | None = None,
        model_name: str | None = None,
        client: AsyncOpenAI | None = None,
    ) -> None:
        resolved_url = base_url or settings.LOCAL_LLM_URL
        resolved_model = model_name or settings.LOCAL_LLM_MODEL
        super().__init__(
            api_key="ollama-local",
            model_name=resolved_model,
            base_url=resolved_url,
            client=client,
        )
