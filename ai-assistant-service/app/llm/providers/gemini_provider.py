import base64
import uuid
from typing import Any, AsyncGenerator
from google import genai
from google.genai import types

from app.core.config import settings
from app.core.exceptions import TransientException
from app.llm.base import (
    AgentResponse,
    BaseLLMProvider,
    ChatMessage,
    ToolCallRequest,
    ToolDefinition,
)


class GeminiProvider(BaseLLMProvider):
    """Google Gemini (Gemini 2.0 Flash / Pro) provider supporting Function Calling and Multimodal Vision."""

    provider_name = "gemini"

    def __init__(
        self,
        api_key: str | None = None,
        model_name: str | None = None,
        client: Any | None = None,
    ) -> None:
        self.api_key = api_key if api_key is not None else settings.GEMINI_API_KEY
        self.model_name = model_name or settings.GEMINI_MODEL
        self._client = client

    def _get_client(self) -> Any:
        if self._client is None:
            self._client = genai.Client(api_key=self.api_key or "dummy-key")
        return self._client

    @staticmethod
    def _build_contents_and_system(
        messages: list[ChatMessage],
    ) -> tuple[str | None, list[Any]]:
        system_parts: list[str] = []
        contents: list[Any] = []

        for msg in messages:
            if msg.role == "system":
                if msg.content:
                    system_parts.append(msg.content)
                continue

            if msg.role == "tool":
                part = types.Part.from_function_response(
                    name=msg.tool_name or "tool_execution",
                    response={"result": msg.content},
                )
                contents.append(types.Content(role="user", parts=[part]))
                continue

            role = "model" if msg.role == "assistant" else "user"
            parts: list[Any] = []

            if msg.content:
                parts.append(types.Part.from_text(text=msg.content))

            for img in msg.images:
                if img.base64_data:
                    raw_bytes = base64.b64decode(img.base64_data)
                    parts.append(
                        types.Part.from_bytes(data=raw_bytes, mime_type=img.media_type)
                    )

            for tc in msg.tool_calls:
                parts.append(
                    types.Part.from_function_call(
                        name=tc.tool_name,
                        args=tc.arguments,
                    )
                )

            if parts:
                contents.append(types.Content(role=role, parts=parts))

        system_instruction = "\n\n".join(system_parts) if system_parts else None
        return system_instruction, contents

    @staticmethod
    def _build_tools(tools: list[ToolDefinition] | None) -> list[types.Tool] | None:
        if not tools:
            return None
        declarations = [
            types.FunctionDeclaration(
                name=t.name,
                description=t.description,
                parameters_json_schema=t.parameters,
            )
            for t in tools
        ]
        return [types.Tool(function_declarations=declarations)]

    async def chat(
        self,
        messages: list[ChatMessage],
        tools: list[ToolDefinition] | None = None,
        temperature: float = 0.2,
    ) -> AgentResponse:
        system_instruction, contents = self._build_contents_and_system(messages)
        gemini_tools = self._build_tools(tools)

        config = types.GenerateContentConfig(
            temperature=temperature,
            system_instruction=system_instruction,
            tools=gemini_tools,
        )

        try:
            client = self._get_client()
            response = await client.aio.models.generate_content(
                model=self.model_name,
                contents=contents,
                config=config,
            )
        except Exception as exc:
            raise TransientException(f"Google Gemini API error: {exc}") from exc

        tool_calls: list[ToolCallRequest] = []
        if getattr(response, "function_calls", None):
            for fc in response.function_calls:
                tool_calls.append(
                    ToolCallRequest(
                        id=getattr(fc, "id", None) or f"gemini_call_{uuid.uuid4().hex[:8]}",
                        tool_name=fc.name,
                        arguments=dict(fc.args or {}),
                    )
                )

        text_content = ""
        try:
            text_content = response.text or ""
        except Exception:
            text_content = ""

        return AgentResponse(
            content=text_content.strip(),
            tool_calls=tool_calls,
            finish_reason="tool_calls" if tool_calls else "stop",
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
