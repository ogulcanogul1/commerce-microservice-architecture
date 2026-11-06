from unittest.mock import AsyncMock, MagicMock
import pytest

from app.core.config import settings
from app.llm.base import ChatMessage
from app.llm.providers.claude_provider import ClaudeProvider
from app.llm.providers.gemini_provider import GeminiProvider
from app.llm.providers.openai_provider import OpenAIProvider


@pytest.mark.anyio
async def test_openai_provider_passes_max_tokens_and_parses_usage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "sk-mock-key")
    provider = OpenAIProvider()

    # Mock OpenAI chat completion response
    mock_choice = MagicMock()
    mock_choice.message.content = "Test cevabı"
    mock_choice.message.tool_calls = None

    mock_usage = MagicMock()
    mock_usage.prompt_tokens = 42
    mock_usage.completion_tokens = 15

    mock_response = MagicMock()
    mock_response.choices = [mock_choice]
    mock_response.usage = mock_usage

    mock_create = AsyncMock(return_value=mock_response)
    monkeypatch.setattr(provider.client.chat.completions, "create", mock_create)

    messages = [ChatMessage(role="user", content="Merhaba")]
    result = await provider.generate(messages, max_tokens=250, temperature=0.1)

    assert result.content == "Test cevabı"
    assert result.provider == "openai"
    assert result.usage is not None
    assert result.usage.input_tokens == 42
    assert result.usage.output_tokens == 15

    # max_tokens kwargs doğrula
    mock_create.assert_called_once()
    _, kwargs = mock_create.call_args
    assert kwargs["max_completion_tokens"] == 250
    assert "max_tokens" not in kwargs
    assert kwargs["temperature"] == 0.1


@pytest.mark.anyio
async def test_claude_provider_passes_max_tokens_and_parses_usage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "sk-ant-mock-key")
    provider = ClaudeProvider()

    mock_block = MagicMock()
    mock_block.type = "text"
    mock_block.text = "Claude yanıtı"

    mock_usage = MagicMock()
    mock_usage.input_tokens = 80
    mock_usage.output_tokens = 25

    mock_response = MagicMock()
    mock_response.content = [mock_block]
    mock_response.usage = mock_usage

    mock_create = AsyncMock(return_value=mock_response)
    monkeypatch.setattr(provider.client.messages, "create", mock_create)

    messages = [ChatMessage(role="user", content="Test")]
    result = await provider.generate(messages, max_tokens=300)

    assert result.content == "Claude yanıtı"
    assert result.provider == "claude"
    assert result.usage is not None
    assert result.usage.input_tokens == 80
    assert result.usage.output_tokens == 25

    mock_create.assert_called_once()
    _, kwargs = mock_create.call_args
    assert kwargs["max_tokens"] == 300


@pytest.mark.anyio
async def test_gemini_provider_passes_max_tokens_and_parses_usage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "mock-gemini-key")
    provider = GeminiProvider()

    mock_response = MagicMock()
    mock_response.function_calls = None
    mock_response.text = "Gemini yanıtı"

    mock_usage = MagicMock()
    mock_usage.prompt_token_count = 55
    mock_usage.candidates_token_count = 33
    mock_response.usage_metadata = mock_usage

    mock_generate = AsyncMock(return_value=mock_response)
    monkeypatch.setattr(provider.client.aio.models, "generate_content", mock_generate)

    messages = [ChatMessage(role="user", content="Soru")]
    result = await provider.generate(messages, max_tokens=150)

    assert result.content == "Gemini yanıtı"
    assert result.provider == "gemini"
    assert result.usage is not None
    assert result.usage.input_tokens == 55
    assert result.usage.output_tokens == 33

    mock_generate.assert_called_once()
    _, kwargs = mock_generate.call_args
    assert kwargs["config"].max_output_tokens == 150
