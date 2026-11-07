import json
import logging
from typing import Any

from openai import AsyncOpenAI

from app.core.config import settings
from app.llm.base import (
    BaseLLMProvider,
    ChatMessage,
    LLMResponse,
    TokenUsage,
    ToolCallRequest,
    ToolDefinition,
)

logger = logging.getLogger(__name__)


class OpenAIProvider(BaseLLMProvider):
    """
    Official OpenAI cloud provider (GPT-4o, GPT-4o-mini, etc.).
    Requires a valid OPENAI_API_KEY in settings / .env.
    """

    provider = "openai"

    def __init__(
        self,
        model_name: str = "gpt-4o-mini",
        api_key: str | None = None,
    ) -> None:
        resolved_key = api_key or settings.OPENAI_API_KEY
        if not resolved_key:
            raise ValueError("OpenAI API key is missing! Please set OPENAI_API_KEY in your .env file.")

        super().__init__(model_name=model_name, api_key=resolved_key)
        self.client = AsyncOpenAI(api_key=self.api_key)

    def _convert_tools(self, tools: list[ToolDefinition]) -> list[dict[str, Any]]:
        """Convert standard ToolDefinition objects into OpenAI-compatible tool schemas."""
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

    async def generate(
        self,
        messages: list[ChatMessage],
        tools: list[ToolDefinition] | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        """
        Execute an asynchronous chat completion request against OpenAI.
        """
        formatted_messages: list[dict[str, Any]] = []
        for msg in messages:
            if msg.role == "assistant" and msg.tool_calls:
                formatted_messages.append(
                    {
                        "role": "assistant",
                        "content": msg.content or None,
                        "tool_calls": [
                            {
                                "id": call.call_id,
                                "type": "function",
                                "function": {
                                    "name": call.tool_name,
                                    "arguments": json.dumps(call.arguments, ensure_ascii=False),
                                },
                            }
                            for call in msg.tool_calls
                        ],
                    }
                )
            elif msg.role == "tool":
                formatted_messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": msg.tool_call_id,
                        "content": msg.content,
                    }
                )
            else:
                formatted_messages.append({"role": msg.role, "content": msg.content})

        kwargs: dict[str, Any] = {
            "model": self.model_name,
            "messages": formatted_messages,
            "temperature": temperature,
        }

        if max_tokens is not None:
            # max_tokens eski; yeni modeller yalnızca max_completion_tokens kabul eder
            kwargs["max_completion_tokens"] = max_tokens

        if tools:
            kwargs["tools"] = self._convert_tools(tools)
            kwargs["tool_choice"] = "auto"

        try:
            response = await self.client.chat.completions.create(**kwargs)
        except Exception as e:
            logger.error("OpenAI API call failed: %s", e)
            raise e

        choice = response.choices[0]
        message = choice.message
        content = message.content or ""
        tool_calls: list[ToolCallRequest] = []

        if message.tool_calls:
            for call in message.tool_calls:
                try:
                    args = json.loads(call.function.arguments)
                except Exception:
                    args = {}

                tool_calls.append(
                    ToolCallRequest(
                        call_id=call.id,
                        tool_name=call.function.name,
                        arguments=args,
                    )
                )

        usage: TokenUsage | None = None
        if getattr(response, "usage", None):
            usage = TokenUsage(
                input_tokens=getattr(response.usage, "prompt_tokens", None),
                output_tokens=getattr(response.usage, "completion_tokens", None),
            )

        return LLMResponse(
            content=content,
            tool_calls=tool_calls,
            provider="openai",
            model=self.model_name,
            usage=usage,
        )
