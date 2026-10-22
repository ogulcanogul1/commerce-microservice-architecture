import json
import uuid
from collections.abc import AsyncGenerator
from typing import Any

from openai import AsyncOpenAI

from app.core.config import settings
from app.core.exceptions import TransientException
from app.llm.base import (
    AgentResponse,
    BaseLLMProvider,
    ChatMessage,
    ToolCallRequest,
    ToolDefinition,
)


class OpenAIProvider(BaseLLMProvider):
    """OpenAI GPT-4o / GPT-4o-mini provider supporting Function Calling and Vision."""

    provider_name = "openai"

    def __init__(
        self,
        api_key: str | None = None,
        model_name: str | None = None,
        base_url: str | None = None,
        client: AsyncOpenAI | None = None,
    ) -> None:
        self.api_key = api_key if api_key is not None else settings.OPENAI_API_KEY
        self.model_name = model_name or settings.OPENAI_MODEL
        self.base_url = base_url
        self._client = client or AsyncOpenAI(
            api_key=self.api_key or "dummy-key",
            base_url=self.base_url,
        )

    @staticmethod
    def _convert_messages(messages: list[ChatMessage]) -> list[dict[str, Any]]:
        openai_messages: list[dict[str, Any]] = []
        for msg in messages:
            if msg.role == "tool":
                openai_messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": msg.tool_call_id or "call_1",
                        "content": msg.content,
                    }
                )
            elif msg.role == "assistant" and msg.tool_calls:
                openai_messages.append(
                    {
                        "role": "assistant",
                        "content": msg.content or None,
                        "tool_calls": [
                            {
                                "id": tc.id or f"call_{uuid.uuid4().hex[:10]}",
                                "type": "function",
                                "function": {
                                    "name": tc.tool_name,
                                    "arguments": json.dumps(tc.arguments),
                                },
                            }
                            for tc in msg.tool_calls
                        ],
                    }
                )
            elif msg.role == "user" and msg.images:
                content_parts: list[dict[str, Any]] = []
                if msg.content:
                    content_parts.append({"type": "text", "text": msg.content})
                for img in msg.images:
                    image_url = img.url or f"data:{img.media_type};base64,{img.base64_data}"
                    content_parts.append(
                        {
                            "type": "image_url",
                            "image_url": {"url": image_url},
                        }
                    )
                openai_messages.append({"role": "user", "content": content_parts})
            else:
                openai_messages.append({"role": msg.role, "content": msg.content})
        return openai_messages

    @staticmethod
    def _convert_tools(tools: list[ToolDefinition] | None) -> list[dict[str, Any]]:
        if not tools:
            return []
        return [
            {
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.description,
                    "parameters": t.parameters,
                },
            }
            for t in tools
        ]

    async def chat(
        self,
        messages: list[ChatMessage],
        tools: list[ToolDefinition] | None = None,
        temperature: float = 0.2,
    ) -> AgentResponse:
        openai_messages = self._convert_messages(messages)
        openai_tools = self._convert_tools(tools)

        kwargs: dict[str, Any] = {
            "model": self.model_name,
            "messages": openai_messages,
            "temperature": temperature,
        }
        if openai_tools:
            kwargs["tools"] = openai_tools

        try:
            completion = await self._client.chat.completions.create(**kwargs)
        except Exception as exc:
            raise TransientException(f"{self.provider_name} API error: {exc}") from exc

        choice = completion.choices[0]
        message = choice.message
        parsed_tool_calls: list[ToolCallRequest] = []

        if getattr(message, "tool_calls", None):
            for tc in message.tool_calls:
                raw_args = tc.function.arguments or "{}"
                try:
                    args_dict = json.loads(raw_args) if isinstance(raw_args, str) else dict(raw_args)
                except json.JSONDecodeError:
                    args_dict = {}
                parsed_tool_calls.append(
                    ToolCallRequest(
                        id=tc.id or f"call_{uuid.uuid4().hex[:8]}",
                        tool_name=tc.function.name,
                        arguments=args_dict,
                    )
                )

        return AgentResponse(
            content=message.content or "",
            tool_calls=parsed_tool_calls,
            finish_reason=choice.finish_reason or "stop",
            provider_used=self.provider_name,
            model_used=self.model_name,
        )

    async def stream_chat(
        self,
        messages: list[ChatMessage],
        tools: list[ToolDefinition] | None = None,
        temperature: float = 0.2,
    ) -> AsyncGenerator[str, None]:
        response = await self.chat(messages=messages, tools=tools, temperature=temperature)
        if response.content:
            for word in response.content.split(" "):
                yield word + " "
