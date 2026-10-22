import uuid
from typing import Any, AsyncGenerator
from anthropic import AsyncAnthropic

from app.core.config import settings
from app.core.exceptions import TransientException
from app.llm.base import (
    AgentResponse,
    BaseLLMProvider,
    ChatMessage,
    ToolCallRequest,
    ToolDefinition,
)


class ClaudeProvider(BaseLLMProvider):
    """Anthropic Claude 3.5 Sonnet provider supporting Tool Calling and Multimodal Vision."""

    provider_name = "claude"

    def __init__(
        self,
        api_key: str | None = None,
        model_name: str | None = None,
        client: AsyncAnthropic | None = None,
    ) -> None:
        self.api_key = api_key if api_key is not None else settings.ANTHROPIC_API_KEY
        self.model_name = model_name or settings.ANTHROPIC_MODEL
        self._client = client or AsyncAnthropic(api_key=self.api_key or "dummy-key")

    @staticmethod
    def _convert_messages(
        messages: list[ChatMessage],
    ) -> tuple[str | None, list[dict[str, Any]]]:
        system_parts: list[str] = []
        anthropic_messages: list[dict[str, Any]] = []

        for msg in messages:
            if msg.role == "system":
                if msg.content:
                    system_parts.append(msg.content)
                continue

            if msg.role == "tool":
                anthropic_messages.append(
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "tool_result",
                                "tool_use_id": msg.tool_call_id or "tool_call_1",
                                "content": msg.content,
                            }
                        ],
                    }
                )
                continue

            if msg.role == "assistant" and msg.tool_calls:
                blocks: list[dict[str, Any]] = []
                if msg.content:
                    blocks.append({"type": "text", "text": msg.content})
                for tc in msg.tool_calls:
                    blocks.append(
                        {
                            "type": "tool_use",
                            "id": tc.id or f"toolu_{uuid.uuid4().hex[:12]}",
                            "name": tc.tool_name,
                            "input": tc.arguments,
                        }
                    )
                anthropic_messages.append({"role": "assistant", "content": blocks})
                continue

            if msg.role == "user" and msg.images:
                user_blocks: list[dict[str, Any]] = []
                for img in msg.images:
                    if img.base64_data:
                        user_blocks.append(
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": img.media_type,
                                    "data": img.base64_data,
                                },
                            }
                        )
                if msg.content:
                    user_blocks.append({"type": "text", "text": msg.content})
                anthropic_messages.append({"role": "user", "content": user_blocks})
                continue

            anthropic_messages.append({"role": msg.role, "content": msg.content})

        system_prompt = "\n\n".join(system_parts) if system_parts else None
        return system_prompt, anthropic_messages

    @staticmethod
    def _convert_tools(tools: list[ToolDefinition] | None) -> list[dict[str, Any]]:
        if not tools:
            return []
        return [
            {
                "name": t.name,
                "description": t.description,
                "input_schema": t.parameters,
            }
            for t in tools
        ]

    async def chat(
        self,
        messages: list[ChatMessage],
        tools: list[ToolDefinition] | None = None,
        temperature: float = 0.2,
    ) -> AgentResponse:
        system_prompt, anthropic_messages = self._convert_messages(messages)
        anthropic_tools = self._convert_tools(tools)

        kwargs: dict[str, Any] = {
            "model": self.model_name,
            "max_tokens": 2048,
            "temperature": temperature,
            "messages": anthropic_messages,
        }
        if system_prompt:
            kwargs["system"] = system_prompt
        if anthropic_tools:
            kwargs["tools"] = anthropic_tools

        try:
            response = await self._client.messages.create(**kwargs)
        except Exception as exc:
            raise TransientException(f"Anthropic Claude API error: {exc}") from exc

        text_parts: list[str] = []
        tool_calls: list[ToolCallRequest] = []

        for block in response.content:
            block_type = getattr(block, "type", None)
            if block_type == "text":
                text_parts.append(getattr(block, "text", ""))
            elif block_type == "tool_use":
                tool_calls.append(
                    ToolCallRequest(
                        id=getattr(block, "id", f"toolu_{uuid.uuid4().hex[:8]}"),
                        tool_name=getattr(block, "name", ""),
                        arguments=dict(getattr(block, "input", {}) or {}),
                    )
                )

        return AgentResponse(
            content="\n".join(text_parts).strip(),
            tool_calls=tool_calls,
            finish_reason=getattr(response, "stop_reason", "end_turn") or "end_turn",
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
