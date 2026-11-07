import json
from unittest.mock import AsyncMock, MagicMock
import pytest

from app.core.config import settings
from app.llm.base import ChatMessage, ToolCallRequest, ToolDefinition
from app.llm.fake import FakeLLMProvider
from app.llm.providers.claude_provider import ClaudeProvider
from app.llm.providers.gemini_provider import GeminiProvider
from app.llm.providers.local_provider import LocalProvider
from app.llm.providers.openai_provider import OpenAIProvider


@pytest.mark.anyio
async def test_fake_llm_scripted_tool_calls_roundtrip() -> None:
    tool_req = ToolCallRequest(
        call_id="call_ord_1",
        tool_name="get_order",
        arguments={"order_number": "ORD-123"},
    )
    provider = FakeLLMProvider(
        responses=[[tool_req], "Siparişiniz yolda."]
    )

    # Tur 1: Kullanıcı sorar -> Model tool çağrısı döner
    messages = [ChatMessage(role="user", content="Siparişim nerede?")]
    resp1 = await provider.generate(messages)
    assert resp1.content == ""
    assert len(resp1.tool_calls) == 1
    assert resp1.tool_calls[0].call_id == "call_ord_1"
    assert resp1.tool_calls[0].tool_name == "get_order"

    # Tur 2: Tool sonucu geri beslenir -> Model nihai yanıtı döner
    messages.append(
        ChatMessage(
            role="assistant",
            content="",
            tool_calls=[tool_req],
        )
    )
    messages.append(
        ChatMessage(
            role="tool",
            name="get_order",
            tool_call_id="call_ord_1",
            content='{"status": "IN_TRANSIT"}',
        )
    )
    resp2 = await provider.generate(messages)
    assert resp2.content == "Siparişiniz yolda."
    assert resp2.tool_calls == []

    assert len(provider.calls) == 2
    assert len(provider.calls[1]["messages"]) == 3


@pytest.mark.anyio
async def test_openai_provider_message_conversion(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "sk-mock-key")
    provider = OpenAIProvider()

    mock_choice = MagicMock()
    mock_choice.message.content = "Harika, siparişinizi buldum."
    mock_choice.message.tool_calls = None

    mock_response = MagicMock()
    mock_response.choices = [mock_choice]
    mock_response.usage = None

    mock_create = AsyncMock(return_value=mock_response)
    monkeypatch.setattr(provider.client.chat.completions, "create", mock_create)

    messages = [
        ChatMessage(role="user", content="ORD-100 nerede?"),
        ChatMessage(
            role="assistant",
            content="",
            tool_calls=[
                ToolCallRequest(
                    call_id="call_999",
                    tool_name="get_order",
                    arguments={"order_number": "ORD-100"},
                )
            ],
        ),
        ChatMessage(
            role="tool",
            name="get_order",
            tool_call_id="call_999",
            content='{"status": "DELIVERED"}',
        ),
    ]

    result = await provider.generate(messages)
    assert result.content == "Harika, siparişinizi buldum."

    mock_create.assert_called_once()
    _, kwargs = mock_create.call_args
    sent_messages = kwargs["messages"]

    assert len(sent_messages) == 3
    # Assistant mesajı tool_calls taşımalı
    assert sent_messages[1]["role"] == "assistant"
    assert sent_messages[1]["tool_calls"][0]["id"] == "call_999"
    assert sent_messages[1]["tool_calls"][0]["function"]["name"] == "get_order"
    assert sent_messages[1]["tool_calls"][0]["function"]["arguments"] == json.dumps({"order_number": "ORD-100"})

    # Tool mesajı tool_call_id taşımalı
    assert sent_messages[2]["role"] == "tool"
    assert sent_messages[2]["tool_call_id"] == "call_999"
    assert sent_messages[2]["content"] == '{"status": "DELIVERED"}'


@pytest.mark.anyio
async def test_claude_provider_message_conversion_and_tool_merging(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "sk-ant-mock-key")
    provider = ClaudeProvider()

    mock_block = MagicMock()
    mock_block.type = "text"
    mock_block.text = "Sipariş ve kargo durumu alındı."

    mock_response = MagicMock()
    mock_response.content = [mock_block]
    mock_response.usage = None

    mock_create = AsyncMock(return_value=mock_response)
    monkeypatch.setattr(provider.client.messages, "create", mock_create)

    # İki art arda tool mesajı simüle ediyoruz
    messages = [
        ChatMessage(role="system", content="Sen asistansın."),
        ChatMessage(role="user", content="Durum nedir?"),
        ChatMessage(
            role="assistant",
            content="Kontrol ediyorum.",
            tool_calls=[
                ToolCallRequest(call_id="call_1", tool_name="get_order", arguments={"id": "1"}),
                ToolCallRequest(call_id="call_2", tool_name="get_shipment", arguments={"id": "2"}),
            ],
        ),
        ChatMessage(
            role="tool",
            name="get_order",
            tool_call_id="call_1",
            content='{"order": 1}',
        ),
        ChatMessage(
            role="tool",
            name="get_shipment",
            tool_call_id="call_2",
            content='{"shipment": 2}',
        ),
    ]

    result = await provider.generate(messages)
    assert result.content == "Sipariş ve kargo durumu alındı."

    mock_create.assert_called_once()
    _, kwargs = mock_create.call_args
    assert kwargs["system"] == "Sen asistansın."
    anthropic_msgs = kwargs["messages"]

    # Mesajlar: 1. user ("Durum nedir?"), 2. assistant (text + 2 tool_use), 3. user (merged 2 tool_result)
    assert len(anthropic_msgs) == 3
    assert anthropic_msgs[0]["role"] == "user"
    assert anthropic_msgs[1]["role"] == "assistant"
    assert len(anthropic_msgs[1]["content"]) == 3
    assert anthropic_msgs[1]["content"][0]["type"] == "text"
    assert anthropic_msgs[1]["content"][1]["type"] == "tool_use"
    assert anthropic_msgs[1]["content"][1]["id"] == "call_1"

    # Art arda gelen iki tool mesajı tek bir user mesajında birleştirilmiş olmalı
    assert anthropic_msgs[2]["role"] == "user"
    assert isinstance(anthropic_msgs[2]["content"], list)
    assert len(anthropic_msgs[2]["content"]) == 2
    assert anthropic_msgs[2]["content"][0]["type"] == "tool_result"
    assert anthropic_msgs[2]["content"][0]["tool_use_id"] == "call_1"
    assert anthropic_msgs[2]["content"][1]["type"] == "tool_result"
    assert anthropic_msgs[2]["content"][1]["tool_use_id"] == "call_2"


@pytest.mark.anyio
async def test_gemini_provider_message_conversion(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "mock-gemini-key")
    provider = GeminiProvider()

    mock_response = MagicMock()
    mock_response.function_calls = None
    mock_response.text = "Gemini cevabı"
    mock_response.usage_metadata = None

    mock_generate = AsyncMock(return_value=mock_response)
    monkeypatch.setattr(provider.client.aio.models, "generate_content", mock_generate)

    messages = [
        ChatMessage(role="user", content="Sorgu"),
        ChatMessage(
            role="assistant",
            content="Bakıyorum",
            tool_calls=[
                ToolCallRequest(call_id="call_0", tool_name="search_policy", arguments={})
            ],
        ),
        ChatMessage(
            role="tool",
            name="search_policy",
            tool_call_id="call_0",
            content='{"result": "14 gün iade süresi"}',
        ),
    ]

    result = await provider.generate(messages)
    assert result.content == "Gemini cevabı"

    mock_generate.assert_called_once()
    _, kwargs = mock_generate.call_args
    contents = kwargs["contents"]

    assert len(contents) == 3
    # user
    assert contents[0].role == "user"
    # assistant -> model
    assert contents[1].role == "model"
    assert len(contents[1].parts) == 2  # text + function_call
    # tool -> user with function_response
    assert contents[2].role == "user"
    assert len(contents[2].parts) == 1
    assert contents[2].parts[0].function_response.name == "search_policy"
