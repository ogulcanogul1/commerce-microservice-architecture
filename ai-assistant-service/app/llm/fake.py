import asyncio
from collections.abc import Callable
from typing import Any

from app.llm.base import (
    BaseLLMProvider,
    ChatMessage,
    LLMResponse,
    TokenUsage,
    ToolCallRequest,
    ToolDefinition,
)


class FakeLLMProvider(BaseLLMProvider):
    """
    In-memory, deterministic fake LLM provider for networkless testing.
    Records all calls, calculates usage deterministically by word count,
    and supports sequential responses, custom responders, delay, and error injection.
    """

    provider = "fake"

    def __init__(
        self,
        responses: list[str | list[ToolCallRequest]] | None = None,
        responder: Callable[[list[ChatMessage]], str | list[ToolCallRequest]] | None = None,
        model_name: str = "fake-llm",
        raise_on_call: Exception | None = None,
        delay_sec: float = 0.0,
    ) -> None:
        if responses is not None and responder is not None:
            raise ValueError("FakeLLMProvider cannot accept both 'responses' and 'responder'.")

        super().__init__(model_name=model_name)
        self._has_responses = responses is not None
        self.responses: list[str | list[ToolCallRequest]] = (
            list(responses) if responses is not None else []
        )
        self.responder = responder
        self.raise_on_call = raise_on_call
        self.delay_sec = delay_sec
        self.calls: list[dict[str, Any]] = []

    async def generate(
        self,
        messages: list[ChatMessage],
        tools: list[ToolDefinition] | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        self.calls.append(
            {
                "messages": list(messages),
                "tools": list(tools) if tools else None,
                "temperature": temperature,
                "max_tokens": max_tokens,
            }
        )

        if self.delay_sec > 0:
            await asyncio.sleep(self.delay_sec)

        if self.raise_on_call is not None:
            raise self.raise_on_call

        if self.responder is not None:
            raw_result = self.responder(messages)
        elif self.responses:
            raw_result = self.responses.pop(0)
        else:
            raise RuntimeError("FakeLLMProvider: yanıt kalmadı")

        if isinstance(raw_result, LLMResponse):
            return raw_result

        if isinstance(raw_result, list):
            content = ""
            tool_calls = raw_result
        else:
            content = raw_result
            tool_calls = []

        # Deterministic token count based on whitespace separation
        input_tokens = sum(len(m.content.split()) for m in messages if m.content)
        output_tokens = len(content.split()) if content else 0

        return LLMResponse(
            content=content,
            tool_calls=tool_calls,
            provider="fake",
            model=self.model_name,
            usage=TokenUsage(
                input_tokens=input_tokens,
                output_tokens=output_tokens,
            ),
        )
