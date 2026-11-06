import pytest

from app.core.config import settings
from app.llm.factory import LLMFactory
from app.llm.providers.claude_provider import ClaudeProvider
from app.llm.providers.gemini_provider import GeminiProvider
from app.llm.providers.local_provider import LocalProvider
from app.llm.providers.openai_provider import OpenAIProvider


def test_factory_get_provider_with_custom_model_name(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "sk-test-fake-key")
    provider = LLMFactory.get_provider("openai", model_name="gpt-4o-custom")
    assert isinstance(provider, OpenAIProvider)
    assert provider.model_name == "gpt-4o-custom"


def test_factory_aliases(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "sk-ant-test-key")
    monkeypatch.setattr(settings, "LOCAL_LLM_MODEL", "llama3")
    monkeypatch.setattr(settings, "LOCAL_LLM_BASE_URL", "http://localhost:11434/v1")

    # "anthropic" alias
    claude_provider = LLMFactory.get_provider("anthropic", model_name="claude-3-haiku")
    assert isinstance(claude_provider, ClaudeProvider)
    assert claude_provider.model_name == "claude-3-haiku"

    # "ollama" alias
    local_provider = LLMFactory.get_provider("ollama", model_name="mistral")
    assert isinstance(local_provider, LocalProvider)
    assert local_provider.model_name == "mistral"


def test_factory_default_provider_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "DEFAULT_LLM_PROVIDER", "gemini")
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "test-gemini-key")
    provider = LLMFactory.get_provider()
    assert isinstance(provider, GeminiProvider)
    assert provider.model_name == "gemini-2.5-flash"


def test_factory_unsupported_provider_raises_value_error() -> None:
    with pytest.raises(ValueError, match="Unsupported LLM provider"):
        LLMFactory.get_provider("unknown_provider")
