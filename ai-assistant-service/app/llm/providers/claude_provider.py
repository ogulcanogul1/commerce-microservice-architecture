import logging
from typing import Any

from anthropic import AsyncAnthropic

from app.core.config import settings
from app.llm.base import (
    BaseLLMProvider,
    ChatMessage,
    LLMResponse,
    ToolCallRequest,
    ToolDefinition,
)

logger = logging.getLogger(__name__)


class ClaudeProvider(BaseLLMProvider):
    """
    Anthropic Claude cloud provider (Claude 3.5 Sonnet, Haiku, Opus).
    Requires a valid ANTHROPIC_API_KEY in settings / .env.
    """

    def __init__(
        self,
        model_name: str = "claude-3-5-sonnet-20241022",
        api_key: str | None = None,
    ) -> None:
        resolved_key = api_key or settings.ANTHROPIC_API_KEY
        if not resolved_key:
            raise ValueError(
                "Anthropic API key is missing! Please set ANTHROPIC_API_KEY in your .env file."
            )

        super().__init__(model_name=model_name, api_key=resolved_key)
        self.client = AsyncAnthropic(api_key=self.api_key)

    def _convert_tools(self, tools: list[ToolDefinition]) -> list[dict[str, Any]]:
        """
        Convert standard ToolDefinition objects into Anthropic tool schema.
        Note: Anthropic uses 'input_schema' instead of 'parameters'.
        """
        return [
            {
                "name": t.name,
                "description": t.description,
                "input_schema": t.parameters,
            }
            for t in tools
        ]

    async def generate(
        self,
        messages: list[ChatMessage],
        tools: list[ToolDefinition] | None = None,
        temperature: float = 0.7,
    ) -> LLMResponse:
        """
        Execute an asynchronous chat completion request against Anthropic Claude.
        """
        system_prompt: str = ""
        anthropic_messages: list[dict[str, Any]] = []

        for msg in messages:
            if msg.role == "system":
                system_prompt = msg.content
            elif msg.role in ("user", "assistant"):
                anthropic_messages.append({"role": msg.role, "content": msg.content})

        kwargs: dict[str, Any] = {
            "model": self.model_name,
            "messages": anthropic_messages,
            "max_tokens": 4096,
            "temperature": temperature,
        }

        if system_prompt:
            kwargs["system"] = system_prompt

        if tools:
            kwargs["tools"] = self._convert_tools(tools)

        try:
            response = await self.client.messages.create(**kwargs)
        except Exception as e:
            logger.error("Claude API call failed: %s", e)
            raise e

        content_parts: list[str] = []
        tool_calls: list[ToolCallRequest] = []

        for block in response.content:
            if block.type == "text":
                content_parts.append(block.text)
            elif block.type == "tool_use":
                tool_calls.append(
                    ToolCallRequest(
                        call_id=block.id,
                        tool_name=block.name,
                        arguments=block.input if isinstance(block.input, dict) else {},
                    )
                )

        return LLMResponse(
            content="\n".join(content_parts),
            tool_calls=tool_calls,
            provider="claude",
            model=self.model_name,
        )
