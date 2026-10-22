import base64
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.exceptions import BusinessRuleException, TransientException
from app.core.security import RequestContext, set_request_context
from app.llm.base import ChatMessage, ImageAttachment, ToolCallRequest, ToolDefinition
from app.llm.factory import LLMFactory
from app.llm.providers.claude_provider import ClaudeProvider
from app.llm.providers.gemini_provider import GeminiProvider
from app.llm.providers.local_provider import LocalProvider
from app.llm.providers.openai_provider import OpenAIProvider


def _sample_tools() -> list[ToolDefinition]:
    return [
        ToolDefinition(
            name="get_latest_order",
            description="Retrieves the latest order for the authenticated customer",
            parameters={
                "type": "object",
                "properties": {"limit": {"type": "integer"}},
                "required": [],
            },
        )
    ]


def test_llm_factory_resolves_all_supported_providers():
    assert isinstance(LLMFactory.get_provider("claude"), ClaudeProvider)
    assert isinstance(LLMFactory.get_provider("openai"), OpenAIProvider)
    assert isinstance(LLMFactory.get_provider("gemini"), GeminiProvider)
    assert isinstance(LLMFactory.get_provider("local"), LocalProvider)
    assert isinstance(LLMFactory.get_provider("ollama"), LocalProvider)


def test_llm_factory_respects_request_context_header():
    token = set_request_context(RequestContext(model_provider="claude"))
    try:
        provider = LLMFactory.get_provider()
        assert isinstance(provider, ClaudeProvider)
    finally:
        from app.core.security import _request_context_var
        _request_context_var.reset(token)


def test_llm_factory_raises_non_retryable_business_rule_on_invalid_provider():
    with pytest.raises(BusinessRuleException) as exc_info:
        LLMFactory.get_provider("grok-999")
    assert exc_info.value.status_code == 400
    assert "Unsupported LLM provider" in exc_info.value.detail


@pytest.mark.asyncio
async def test_claude_provider_tool_calling_and_multimodal():
    mock_client = MagicMock()
    mock_client.messages.create = AsyncMock(
        return_value=SimpleNamespace(
            stop_reason="tool_use",
            content=[
                SimpleNamespace(type="text", text="Siparişinizi kontrol ediyorum."),
                SimpleNamespace(
                    type="tool_use",
                    id="toolu_123",
                    name="get_latest_order",
                    input={"limit": 1},
                ),
            ],
        )
    )
    provider = ClaudeProvider(api_key="test-key", client=mock_client)

    img = ImageAttachment(
        media_type="image/png",
        base64_data=base64.b64encode(b"fake-image").decode("utf-8"),
    )
    messages = [
        ChatMessage(role="system", content="Sen bir e-ticaret asistanısın."),
        ChatMessage(role="user", content="Son siparişim nerede?", images=[img]),
    ]

    result = await provider.chat(messages=messages, tools=_sample_tools())
    assert result.provider_used == "claude"
    assert result.content == "Siparişinizi kontrol ediyorum."
    assert len(result.tool_calls) == 1
    assert result.tool_calls[0].tool_name == "get_latest_order"
    assert result.tool_calls[0].arguments == {"limit": 1}


@pytest.mark.asyncio
async def test_openai_and_local_provider_tool_calling_and_streaming():
    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(
        return_value=SimpleNamespace(
            choices=[
                SimpleNamespace(
                    finish_reason="tool_calls",
                    message=SimpleNamespace(
                        content="Kargo durumunu sorguluyorum.",
                        tool_calls=[
                            SimpleNamespace(
                                id="call_abc",
                                function=SimpleNamespace(
                                    name="get_latest_order",
                                    arguments='{"limit": 1}',
                                ),
                            )
                        ],
                    ),
                )
            ]
        )
    )

    provider = OpenAIProvider(api_key="test-key", client=mock_client)
    messages = [
        ChatMessage(role="system", content="System prompt"),
        ChatMessage(role="user", content="Siparişim nerede?"),
        ChatMessage(
            role="assistant",
            content="",
            tool_calls=[ToolCallRequest(id="call_1", tool_name="get_latest_order", arguments={})],
        ),
        ChatMessage(role="tool", tool_call_id="call_1", content='{"orderNumber": "ORD-101"}'),
    ]

    result = await provider.chat(messages=messages, tools=_sample_tools())
    assert result.provider_used == "openai"
    assert len(result.tool_calls) == 1
    assert result.tool_calls[0].tool_name == "get_latest_order"

    chunks = [chunk async for chunk in provider.stream_chat(messages=messages)]
    assert "".join(chunks).strip() == "Kargo durumunu sorguluyorum."

    local_provider = LocalProvider(client=mock_client)
    local_res = await local_provider.chat(messages=messages)
    assert local_res.provider_used == "local"


@pytest.mark.asyncio
async def test_gemini_provider_tool_calling_and_error_wrapping():
    mock_client = MagicMock()
    mock_client.aio.models.generate_content = AsyncMock(
        return_value=SimpleNamespace(
            text="Kargonuz dağıtımda.",
            function_calls=[
                SimpleNamespace(
                    id="fc_1",
                    name="get_latest_order",
                    args={"limit": 1},
                )
            ],
        )
    )

    provider = GeminiProvider(api_key="test-key", client=mock_client)
    messages = [
        ChatMessage(role="system", content="Sen asistansın."),
        ChatMessage(role="user", content="Siparişim nerede?"),
    ]

    result = await provider.chat(messages=messages, tools=_sample_tools())
    assert result.provider_used == "gemini"
    assert result.content == "Kargonuz dağıtımda."
    assert len(result.tool_calls) == 1
    assert result.tool_calls[0].tool_name == "get_latest_order"

    # Verify transient failure raises Retryable TransientException
    mock_client.aio.models.generate_content = AsyncMock(side_effect=RuntimeError("API quota timeout"))
    with pytest.raises(TransientException):
        await provider.chat(messages=messages)
