"""Registry and execution engine for agentic tools.

Handles argument validation, execution timeouts, error translation (preventing IDOR leaks),
and indirect prompt injection escaping via render_for_model.
"""

import asyncio
import json
import logging
import time
from typing import Any
from pydantic import ValidationError

from app.agent.tools.base import Tool, ToolContext, ToolResult
from app.clients.base import (
    DownstreamBadRequest,
    DownstreamForbidden,
    DownstreamNotFound,
    DownstreamUnavailable,
)
from app.core.audit import (
    DENY_OUTCOMES,
    OUTCOME_BAD_REQUEST,
    OUTCOME_DENIED,
    OUTCOME_ERROR,
    OUTCOME_INVALID_ARGS,
    OUTCOME_NOT_FOUND,
    OUTCOME_OK,
    OUTCOME_TIMEOUT,
    OUTCOME_UNAVAILABLE,
    hash_args,
    record_denied_access,
    write_audit,
)
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
        """Merkezi Araç Çalıştırıcı ve Audit Sarmalayıcısı.

        Tüm araç çağrıları bu metot üzerinden geçer:
        1. Başlangıç zamanını monotonic saatle alır.
        2. _execute_core ile asıl çalıştırma ve parametre doğrulamasını yapar.
        3. Sonuç başarılı veya hatalı olsa dahi (finally bloğunda) mutlaka 'tool_call' audit kaydı düşer.
        4. Sonuç bir yetkisiz erişim veya tarama ise DenyTracker sayacını günceller.
        """
        started = time.monotonic()
        outcome = OUTCOME_ERROR
        try:
            result = await self._execute_core(name, raw_args, ctx)
            outcome = result.reason or (OUTCOME_OK if result.ok else OUTCOME_ERROR)
            return result
        except asyncio.TimeoutError:
            outcome = OUTCOME_TIMEOUT
            raise
        except DownstreamUnavailable:
            outcome = OUTCOME_UNAVAILABLE
            raise
        except asyncio.CancelledError:
            outcome = OUTCOME_TIMEOUT
            raise
        except Exception:
            outcome = OUTCOME_ERROR
            raise
        finally:
            try:
                await asyncio.shield(self._record_audit(name, raw_args, ctx, outcome, started))
            except Exception:
                pass

    async def _record_audit(
        self,
        name: str,
        raw_args: Any,
        ctx: ToolContext,
        outcome: str,
        started: float,
    ) -> None:
        """Her araç çağrısı için PII içermeyen standart bir denetim kaydı yazar."""
        safe_tool_name = str(name)[:64]
        try:
            arg_names = (
                sorted(str(k)[:64] for k in raw_args.keys())[:32]
                if isinstance(raw_args, dict)
                else []
            )
        except Exception:
            arg_names = []

        # 1. PII içermeyen güvenli audit kaydı bas (argüman değerleri yerine hash ve süre yazılır)
        write_audit(
            "tool_call",
            user_id=ctx.user_id,
            correlation_id=ctx.correlation_id,
            outcome=outcome,
            tool=safe_tool_name,
            arg_names=arg_names,
            args_hash=hash_args(raw_args),
            ms=round((time.monotonic() - started) * 1000),
        )
        # 2. Eğer sonuç şüpheli bir yetki ihlali veya tarama ise enumeration sayacına işlet
        if outcome in DENY_OUTCOMES:
            await record_denied_access(ctx.user_id, ctx.correlation_id)

    async def _execute_core(
        self,
        name: str,
        raw_args: dict[str, Any],
        ctx: ToolContext,
    ) -> ToolResult:
        """Validate input arguments, run tool with timeout, and handle exceptions safely."""
        tool = self._tools.get(name)
        if tool is None:
            return ToolResult(ok=False, error=f"Bilinmeyen araç: {name}", reason=OUTCOME_INVALID_ARGS)

        parsed_args = raw_args
        if isinstance(raw_args, str):
            try:
                parsed_args = json.loads(raw_args)
            except (json.JSONDecodeError, ValueError) as e:
                logger.warning("Tool '%s' raw_args JSON decoding failed: %s", name, e)
                return ToolResult(ok=False, error="Geçersiz araç parametreleri (JSON format hatası).", reason=OUTCOME_INVALID_ARGS)

        if not isinstance(parsed_args, dict):
            return ToolResult(ok=False, error="Geçersiz araç parametreleri (parametreler sözlük formatında olmalıdır).", reason=OUTCOME_INVALID_ARGS)

        try:
            validated_args = tool.args_model.model_validate(parsed_args)
        except ValidationError as e:
            # Dahili Python türlerini veya ham girdi değerlerini sızdırmadan yalnızca parametre alanlarını özetle
            invalid_fields = [
                ".".join(str(p) for p in err.get("loc", []) if str(p) != "__root__")
                for err in e.errors()
            ]
            fields_str = ", ".join(f for f in invalid_fields if f)
            error_types = [err.get("type") for err in e.errors()]
            logger.warning(
                "Tool '%s' validation failed for fields: %s (types: %s)",
                name,
                fields_str or "unknown",
                error_types,
            )
            if fields_str:
                return ToolResult(ok=False, error=f"Geçersiz araç parametreleri ({fields_str})", reason=OUTCOME_INVALID_ARGS)
            return ToolResult(ok=False, error="Geçersiz araç parametreleri.", reason=OUTCOME_INVALID_ARGS)
        except (json.JSONDecodeError, ValueError) as exc:
            logger.warning("Tool '%s' parameter decode failed: %s", name, type(exc).__name__)
            return ToolResult(ok=False, error="Geçersiz araç parametreleri.", reason=OUTCOME_INVALID_ARGS)
        except Exception as exc:
            logger.warning("Tool '%s' unexpected parameter validation exception: %s", name, type(exc).__name__)
            return ToolResult(ok=False, error="Geçersiz araç parametreleri.", reason=OUTCOME_INVALID_ARGS)

        timeout = getattr(tool, "timeout_sec", None) or self._timeout_sec
        try:
            return await asyncio.wait_for(
                tool.run(validated_args, ctx),
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            logger.warning("Tool '%s' timed out after %s seconds", name, timeout)
            if name == "search_policy":
                raise
            return ToolResult(ok=False, error="Araç zaman aşımına uğradı.", reason=OUTCOME_TIMEOUT)
        except DownstreamNotFound:
            # Varlık sızdırmama kuralı: 404 ve 403 aynı hata metnine çevrilir
            return ToolResult(ok=False, error="Sipariş bulunamadı.", reason=OUTCOME_NOT_FOUND)
        except DownstreamForbidden:
            # Varlık sızdırmama kuralı: 404 ve 403 aynı hata metnine çevrilir
            return ToolResult(ok=False, error="Sipariş bulunamadı.", reason=OUTCOME_DENIED)
        except DownstreamBadRequest as exc:
            return ToolResult(ok=False, error=exc.detail or "Geçersiz işlem parametreleri.", reason=OUTCOME_BAD_REQUEST)
        except DownstreamUnavailable:
            # Altyapı kesintileri HTTP 503 olarak yukarı taşınır
            raise
        except RuntimeError:
            if name == "search_policy":
                # RAG altyapı kesintileri (Qdrant, LLM vb.) gizlenmez; HTTP 503 olarak yukarı taşınır
                raise
            logger.exception("Unexpected error executing tool '%s'", name)
            return ToolResult(ok=False, error="Araç çalıştırılırken bir hata oluştu.", reason=OUTCOME_ERROR)
        except ValueError as exc:
            # Dahili kod ayrıntılarını, stack detaylarını veya kötü niyetli input yankılarını sızdırma
            msg = str(exc)
            logger.warning("Tool '%s' raised ValueError: %s", name, type(exc).__name__)
            if "Geçersiz sipariş numarası" in msg:
                return ToolResult(ok=False, error="Geçersiz sipariş numarası.", reason=OUTCOME_BAD_REQUEST)
            return ToolResult(ok=False, error="Geçersiz parametre veya işlem değeri.", reason=OUTCOME_BAD_REQUEST)
        except Exception as exc:
            logger.exception("Unexpected error executing tool '%s': %s", name, exc)
            return ToolResult(ok=False, error="Araç çalıştırılırken bir hata oluştu.", reason=OUTCOME_ERROR)
