import logging
from typing import Any

from google import genai
from google.genai import types

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


class GeminiProvider(BaseLLMProvider):
    """Google Gemini LLM provider utilizing the modern official google-genai SDK."""

    def __init__(
        self,
        model_name: str = "gemini-2.5-flash",
        api_key: str = "",
        base_url: str = "",
    ) -> None:
        resolved_key = api_key or settings.GEMINI_API_KEY
        if not resolved_key:
            raise ValueError(
                "Gemini API key is missing! Please set GEMINI_API_KEY in your .env file."
            )
        super().__init__(model_name=model_name, api_key=resolved_key, base_url=base_url)
        self.client = genai.Client(api_key=self.api_key)

    def _convert_tools(self, tools: list[ToolDefinition]) -> list[types.Tool]:
        """Convert standard ToolDefinition list into Gemini-compatible FunctionDeclaration objects."""
        declarations = []
        for t in tools:
            declarations.append(
                types.FunctionDeclaration(
                    name=t.name,
                    description=t.description,
                    parameters=t.parameters,
                )
            )
        return [types.Tool(function_declarations=declarations)]

    async def generate(
        self,
        messages: list[ChatMessage],
        tools: list[ToolDefinition] | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        """
        Execute an asynchronous chat completion request against the Gemini API.
        """
        system_instruction: str | None = None
        contents: list[types.Content] = []

        for msg in messages:
            if msg.role == "system":
                system_instruction = msg.content
            elif msg.role == "user":
                contents.append(
                    types.Content(
                        role="user",
                        parts=[types.Part.from_text(text=msg.content)],
                    )
                )
            elif msg.role == "assistant":
                contents.append(
                    types.Content(
                        role="model",
                        parts=[types.Part.from_text(text=msg.content)],
                    )
                )

        config_kwargs: dict[str, Any] = {
            "temperature": temperature,
            "system_instruction": system_instruction,
        }
        if max_tokens is not None:
            config_kwargs["max_output_tokens"] = max_tokens

        config = types.GenerateContentConfig(**config_kwargs)

        if tools:
            config.tools = self._convert_tools(tools)

        try:
            response = await self.client.aio.models.generate_content(
                model=self.model_name,
                contents=contents,
                config=config,
            )
        except Exception as e:
            logger.error("Gemini API call failed: %s", e)
            raise e

        response_text = ""
        tool_calls: list[ToolCallRequest] = []

        if response.function_calls:
            for call in response.function_calls:
                tool_calls.append(
                    ToolCallRequest(
                        call_id=f"call_{call.name}",
                        tool_name=call.name,
                        arguments=dict(call.args) if call.args else {},
                    )
                )
        else:
            response_text = response.text or ""

        usage: TokenUsage | None = None
        if getattr(response, "usage_metadata", None):
            usage = TokenUsage(
                input_tokens=getattr(response.usage_metadata, "prompt_token_count", None),
                output_tokens=getattr(response.usage_metadata, "candidates_token_count", None),
            )

        return LLMResponse(
            content=response_text,
            tool_calls=tool_calls,
            provider="gemini",
            model=self.model_name,
            usage=usage,
        )
