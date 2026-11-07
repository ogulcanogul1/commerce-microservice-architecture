"""Registry and execution engine for agentic tools.

Handles argument validation, execution timeouts, error translation (preventing IDOR leaks),
and indirect prompt injection escaping via render_for_model.
"""

import asyncio
import json
import logging
from typing import Any
from pydantic import ValidationError

from app.agent.tools.base import Tool, ToolContext, ToolResult
from app.clients.base import DownstreamForbidden, DownstreamNotFound
from app.core.config import settings
from app.llm.base import ToolDefinition

logger = logging.getLogger(__name__)


def render_for_model(
    tool_name: str,
    result: ToolResult,
    *,
    max_chars: int | None = None,
) -> str:
    """Format and sanitize tool output for ingestion into LLM context.

    Escapes prompt injection delimiters (<arac_sonucu>) and enforces maximum character limits.
    """
    limit = max_chars if max_chars is not None else settings.AGENT_MAX_TOOL_RESULT_CHARS

    if result.ok:
        content_obj = result.data
    else:
        content_obj = {"error": result.error or "Bilinmeyen hata."}

    raw_json = json.dumps(content_obj, ensure_ascii=False)

    # 1. Uzunluk kontrolü ve kırpma
    if len(raw_json) > limit:
        # 2000 karakter sınırını aşarsa truncated uyarısı ekle
        clipped_text = raw_json[: limit - 60]
        content_obj = {
            "truncated": True,
            "data": clipped_text + "... [kırpıldı]",
        }
        raw_json = json.dumps(content_obj, ensure_ascii=False)

    # 2. Indirect Prompt Injection savunması: <arac_sonucu> ve </arac_sonucu> etiketlerini kaçır
    escaped_json = (
        raw_json.replace("</arac_sonucu>", "‹/arac_sonucu›")
        .replace("<arac_sonucu>", "‹arac_sonucu›")
        .replace("<arac_sonucu ", "‹arac_sonucu ")
    )

    return f'<arac_sonucu tool="{tool_name}">{escaped_json}</arac_sonucu>'


class ToolRegistry:
    """Central registry and execution dispatcher for agentic tools."""

    def __init__(self, timeout_sec: float | None = None) -> None:
        self._tools: dict[str, Tool] = {}
        self._timeout_sec = timeout_sec if timeout_sec is not None else settings.AGENT_TOOL_TIMEOUT_SEC

    def register(self, tool: Tool) -> None:
        """Register a tool instance."""
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool | None:
        """Lookup tool by identifier."""
        return self._tools.get(name)

    def definitions(self) -> list[ToolDefinition]:
        """Return schema definitions for all registered tools."""
        return [tool.definition() for tool in self._tools.values()]

    async def execute(
        self,
        name: str,
        raw_args: dict[str, Any],
        ctx: ToolContext,
    ) -> ToolResult:
        """Validate input arguments, run tool with timeout, and handle exceptions safely."""
        tool = self._tools.get(name)
        if tool is None:
            return ToolResult(ok=False, error=f"Bilinmeyen araç: {name}")

        try:
            validated_args = tool.args_model.model_validate(raw_args)
        except ValidationError as e:
            # Model ekstra veya hatalı alan girdiyse değer sızdırmadan alan adı ve hatayı özetle
            error_details = []
            for err in e.errors():
                loc = ".".join(str(p) for p in err.get("loc", []))
                msg = err.get("msg", "geçersiz değer")
                error_details.append(f"{loc}: {msg}")
            return ToolResult(ok=False, error=f"Geçersiz araç parametreleri ({', '.join(error_details)})")
        except Exception:
            return ToolResult(ok=False, error="Geçersiz araç parametreleri.")

        try:
            return await asyncio.wait_for(
                tool.run(validated_args, ctx),
                timeout=self._timeout_sec,
            )
        except asyncio.TimeoutError:
            logger.warning("Tool '%s' timed out after %s seconds", name, self._timeout_sec)
            return ToolResult(ok=False, error="Araç zaman aşımına uğradı.")
        except (DownstreamNotFound, DownstreamForbidden):
            # Varlık sızdırmama kuralı: 404 ve 403 aynı hata metnine çevrilir
            return ToolResult(ok=False, error="Sipariş bulunamadı.")
        except Exception as exc:
            logger.exception("Unexpected error executing tool '%s': %s", name, exc)
            return ToolResult(ok=False, error="Araç çalıştırılırken bir hata oluştu.")
