from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

import httpx

from app.core.config import settings
from app.core.exceptions import (
    AccessDeniedException,
    BusinessRuleException,
    ResourceNotFoundException,
    TransientException,
)
from app.core.security import (
    CORRELATION_ID_HEADER,
    GATEWAY_SECRET_HEADER,
    USER_EMAIL_HEADER,
    USER_ID_HEADER,
    USER_ROLES_HEADER,
    get_request_context,
)
from app.llm.base import ToolDefinition

ToolHandler = Callable[..., Awaitable[dict[str, Any]]]


class CommerceHttpClient:
    """
    Async HTTP client for communicating with downstream Java Spring Boot microservices.
    Automatically propagates X-Gateway-Secret, X-User-Id, X-User-Roles, and X-Correlation-Id
    while mapping HTTP error status codes to Retryable / NonRetryable domain exceptions.
    """

    def __init__(
        self,
        timeout_seconds: float = 5.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.timeout_seconds = timeout_seconds
        self._transport = transport

    @staticmethod
    def build_internal_headers() -> dict[str, str]:
        ctx = get_request_context()
        headers: dict[str, str] = {
            GATEWAY_SECRET_HEADER: settings.GATEWAY_INTERNAL_SECRET,
            CORRELATION_ID_HEADER: ctx.correlation_id,
            "Accept": "application/json",
        }
        if ctx.user_id:
            headers[USER_ID_HEADER] = ctx.user_id
        if ctx.user_email:
            headers[USER_EMAIL_HEADER] = ctx.user_email
        if ctx.user_roles:
            headers[USER_ROLES_HEADER] = ctx.user_roles
        return headers

    async def request(
        self,
        method: str,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        headers = self.build_internal_headers()
        try:
            async with httpx.AsyncClient(
                timeout=self.timeout_seconds,
                transport=self._transport,
            ) as client:
                response = await client.request(
                    method=method,
                    url=url,
                    headers=headers,
                    params=params,
                    json=json_body,
                )
        except httpx.RequestError as exc:
            raise TransientException(
                f"Downstream service communication error for {method} {url}: {exc}"
            ) from exc

        if response.status_code == 403:
            raise AccessDeniedException(
                self._extract_error_detail(response, "Access denied by downstream service")
            )
        if response.status_code == 404:
            raise ResourceNotFoundException(
                self._extract_error_detail(response, f"Requested resource not found at {url}")
            )
        if 400 <= response.status_code < 500:
            raise BusinessRuleException(
                detail=self._extract_error_detail(response, "Client or business validation failed"),
                status_code=response.status_code,
            )
        if response.status_code >= 500:
            raise TransientException(
                detail=self._extract_error_detail(
                    response, f"Downstream service returned HTTP {response.status_code}"
                )
            )

        if response.status_code == 204 or not response.content:
            return {}
        return response.json()

    async def get(self, url: str, *, params: dict[str, Any] | None = None) -> dict[str, Any]:
        return await self.request("GET", url, params=params)

    async def post(self, url: str, *, json_body: dict[str, Any] | None = None) -> dict[str, Any]:
        return await self.request("POST", url, json_body=json_body)

    @staticmethod
    def _extract_error_detail(response: httpx.Response, fallback: str) -> str:
        try:
            data = response.json()
            if isinstance(data, dict):
                return str(data.get("detail") or data.get("message") or fallback)
        except Exception:
            pass
        return fallback


@dataclass
class RegisteredTool:
    definition: ToolDefinition
    handler: ToolHandler


class ToolRegistry:
    """Central registry of agentic tools exposed to the LLM."""

    def __init__(self) -> None:
        self._tools: dict[str, RegisteredTool] = {}

    def register(
        self,
        *,
        name: str,
        description: str,
        parameters: dict[str, Any],
    ) -> Callable[[ToolHandler], ToolHandler]:
        def decorator(func: ToolHandler) -> ToolHandler:
            self._tools[name] = RegisteredTool(
                definition=ToolDefinition(
                    name=name,
                    description=description,
                    parameters=parameters,
                ),
                handler=func,
            )
            return func

        return decorator

    def get_definitions(self) -> list[ToolDefinition]:
        return [item.definition for item in self._tools.values()]

    def has_tool(self, name: str) -> bool:
        return name in self._tools

    async def execute(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if name not in self._tools:
            raise BusinessRuleException(f"Unknown tool requested by model: '{name}'")
        tool = self._tools[name]
        return await tool.handler(**arguments)


http_client = CommerceHttpClient()
tool_registry = ToolRegistry()


def set_http_client(client: CommerceHttpClient) -> None:
    """Allows injecting a custom or mock CommerceHttpClient during testing."""
    global http_client
    http_client = client
