"""AgentService orchestrator implementing the ReAct loop, tool coordination, and grounding.

Executes up to AGENT_MAX_STEPS turns, captures terminal RAG responses, validates numerical
grounding against tool outputs, and emits a structured audit log per request.
"""

import asyncio
import hashlib
import logging
import time
from typing import Any

from app.agent.grounding import check_reply_grounding
from app.agent.models import AgentReply, PendingAction, ReplyKind
from app.agent.prompt import build_agent_messages, build_retry_instruction
from app.agent.tools.base import ToolContext, ToolResult
from app.agent.tools.registry import ToolRegistry, render_for_model
from app.core.config import settings
from app.core.pii import mask_pii
from app.core.security import RequestContext
from app.llm.base import BaseLLMProvider, ChatMessage, TokenUsage

logger = logging.getLogger(__name__)


class AgentService:
    """Core orchestrator driving the conversational customer support agent."""

    def __init__(
        self,
        llm: BaseLLMProvider,
        registry: ToolRegistry,
        *,
        max_steps: int | None = None,
        llm_timeout_sec: float | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        fallback_message: str | None = None,
    ) -> None:
        self._llm = llm
        self._registry = registry
        self._max_steps = max_steps if max_steps is not None else settings.AGENT_MAX_STEPS
        self._llm_timeout_sec = llm_timeout_sec if llm_timeout_sec is not None else settings.AGENT_LLM_TIMEOUT_SEC
        self._temperature = temperature if temperature is not None else settings.AGENT_TEMPERATURE
        self._max_tokens = max_tokens if max_tokens is not None else settings.AGENT_MAX_OUTPUT_TOKENS
        self._fallback_message = fallback_message if fallback_message is not None else settings.AGENT_FALLBACK_MESSAGE

    async def chat(self, message: str, ctx: RequestContext) -> AgentReply:
        """Execute the agent chat turn for the given user message and verified security context."""
        start_time = time.perf_counter()
        llm_time_ms = 0.0
        tool_time_ms = 0.0

        user_id_hash = hashlib.sha256(ctx.user_id.encode("utf-8")).hexdigest()[:12]
        tool_calls_log: list[dict[str, Any]] = []
        captured_pending_action: PendingAction | None = None
        total_input_tokens = 0
        total_output_tokens = 0
        final_kind: ReplyKind = "fallback"
        steps_taken = 0

        # 1. PII Maskeleme (Bundan sonra her aşamada masked kullanılır)
        masked_query, _ = mask_pii(message)
        tool_ctx = ToolContext(
            user_id=ctx.user_id,
            correlation_id=ctx.correlation_id,
            question=masked_query,
        )
        messages = build_agent_messages(masked_query)

        tool_results_text: list[str] = []
        tools_called = False
        grounding_retry_attempted = False

        try:
            step = 0
            while step < self._max_steps:
                step += 1
                steps_taken = step

                # LLM Çağrısı
                t0_llm = time.perf_counter()
                resp = await asyncio.wait_for(
                    self._llm.generate(
                        messages=messages,
                        tools=self._registry.definitions(),
                        temperature=self._temperature,
                        max_tokens=self._max_tokens,
                    ),
                    timeout=self._llm_timeout_sec,
                )
                llm_time_ms += (time.perf_counter() - t0_llm) * 1000.0

                if resp.usage:
                    total_input_tokens += resp.usage.input_tokens or 0
                    total_output_tokens += resp.usage.output_tokens or 0

                # Durum A: Model tool çağırmadı, nihai yanıt metni üretti
                if not resp.tool_calls:
                    final_text = resp.content

                    # Grounding kontrolü: Cevaptaki sayılar araç sonuçlarında var mı?
                    issues = check_reply_grounding(
                        final_text,
                        tool_results_text,
                        tools_called=tools_called,
                    )

                    if issues:
                        if not grounding_retry_attempted and step < self._max_steps:
                            # Modele 1 kez düzeltme fırsatı ver
                            grounding_retry_attempted = True
                            messages.append(ChatMessage(role="assistant", content=final_text))
                            messages.append(build_retry_instruction(issues))
                            continue

                        # Düzeltilemediyse veya adım kalmadıysa güvenli fallback dön
                        final_kind = "fallback"
                        return AgentReply(
                            kind="fallback",
                            reply=self._fallback_message,
                            steps=steps_taken,
                            usage=TokenUsage(
                                input_tokens=total_input_tokens,
                                output_tokens=total_output_tokens,
                            ),
                        )

                    # Grounding başarılı
                    if captured_pending_action is not None:
                        final_kind = "pending_action"
                        # Karar 3 & 6: Onay cümlesi modelin yeniden yazdığı değil, action.summary olmalı
                        return AgentReply(
                            kind="pending_action",
                            reply=captured_pending_action.summary,
                            pending_action=captured_pending_action,
                            steps=steps_taken,
                            usage=TokenUsage(
                                input_tokens=total_input_tokens,
                                output_tokens=total_output_tokens,
                            ),
                        )

                    final_kind = "answer"
                    return AgentReply(
                        kind="answer",
                        reply=final_text,
                        steps=steps_taken,
                        usage=TokenUsage(
                            input_tokens=total_input_tokens,
                            output_tokens=total_output_tokens,
                        ),
                    )

                # Durum B: Model araç çağrıları talep etti
                tools_called = True
                messages.append(
                    ChatMessage(
                        role="assistant",
                        content=resp.content,
                        tool_calls=resp.tool_calls,
                    )
                )

                # Karar 4: search_policy çağrılar arasında varsa yalnızca onu çalıştır
                policy_call = next(
                    (tc for tc in resp.tool_calls if tc.tool_name == "search_policy"),
                    None,
                )

                for idx, call in enumerate(resp.tool_calls):
                    # Provider kontratı: Her call_id için bir tool mesajı dönmek zorunludur
                    if policy_call is not None and call.tool_name != "search_policy":
                        err_res = ToolResult(ok=False, error="search_policy tek başına çağrılmalıdır.")
                        rendered = render_for_model(call.tool_name, err_res)
                        tool_results_text.append(rendered)
                        messages.append(
                            ChatMessage(
                                role="tool",
                                name=call.tool_name,
                                tool_call_id=call.call_id,
                                content=rendered,
                            )
                        )
                        continue

                    # Adım başına maksimum 3 tool çalıştırma sınırı
                    if idx >= 3:
                        err_res = ToolResult(ok=False, error="Tek adımda en fazla 3 araç çağrılabilir.")
                        rendered = render_for_model(call.tool_name, err_res)
                        tool_results_text.append(rendered)
                        messages.append(
                            ChatMessage(
                                role="tool",
                                name=call.tool_name,
                                tool_call_id=call.call_id,
                                content=rendered,
                            )
                        )
                        continue

                    t0_tool = time.perf_counter()
                    result = await self._registry.execute(
                        name=call.tool_name,
                        raw_args=call.arguments,
                        ctx=tool_ctx,
                    )
                    tool_time_ms += (time.perf_counter() - t0_tool) * 1000.0

                    # Güvenlik logu: Argüman değeri kaydedilmez, yalnızca tool adı ve başarı durumu
                    tool_calls_log.append({"name": call.tool_name, "ok": result.ok})

                    rendered = render_for_model(call.tool_name, result)
                    tool_results_text.append(rendered)
                    messages.append(
                        ChatMessage(
                            role="tool",
                            name=call.tool_name,
                            tool_call_id=call.call_id,
                            content=rendered,
                        )
                    )

                    # Terminal RAG cevabı kontrolü: Döngü hemen biter ve cevap aynen verilir
                    if result.terminal_reply is not None:
                        final_kind = result.terminal_reply.kind
                        return AgentReply(
                            kind=result.terminal_reply.kind,
                            reply=result.terminal_reply.reply,
                            citations=result.terminal_reply.citations,
                            steps=steps_taken,
                            usage=TokenUsage(
                                input_tokens=total_input_tokens,
                                output_tokens=total_output_tokens,
                            ),
                        )

                    # Pending Action önerisi yakalandı
                    if result.pending_action is not None:
                        captured_pending_action = result.pending_action

            # Adım limiti aşıldı
            final_kind = "fallback"
            return AgentReply(
                kind="fallback",
                reply=self._fallback_message,
                steps=steps_taken,
                usage=TokenUsage(
                    input_tokens=total_input_tokens,
                    output_tokens=total_output_tokens,
                ),
            )

        finally:
            # Karar 9: İstek başına tek yapılandırılmış güvenlik ve metrik log satırı
            total_duration_ms = (time.perf_counter() - start_time) * 1000.0
            pending_type = (
                captured_pending_action.action_type
                if captured_pending_action
                else None
            )
            logger.info(
                "Agent turn completed: kind=%s, steps=%s, tool_calls=%s, pending_action_type=%s, "
                "input_tokens=%s, output_tokens=%s, latency_ms_total=%.2f, latency_ms_llm=%.2f, "
                "latency_ms_tool=%.2f, provider=%s, model=%s, user_id_hash=%s, correlation_id=%s",
                final_kind,
                steps_taken,
                tool_calls_log,
                pending_type,
                total_input_tokens,
                total_output_tokens,
                total_duration_ms,
                llm_time_ms,
                tool_time_ms,
                getattr(self._llm, "provider", "unknown"),
                getattr(self._llm, "model_name", "unknown"),
                user_id_hash,
                ctx.correlation_id,
            )
