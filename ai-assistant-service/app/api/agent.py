"""Agent HTTP endpoints for conversational chat and human-in-the-loop action confirmation."""

import asyncio
from datetime import datetime
import logging
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException, Path, Request, status
from pydantic import BaseModel, ConfigDict, Field, field_validator
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.agent.executor import ActionExecutor
from app.agent.models import ActionType, ReplyKind
from app.agent.pending import PendingActionStore, PendingActionStoreError
from app.agent.service import AgentService
from app.api.answer import CitationResponse
from app.budget.deps import get_token_budget
from app.budget.estimator import estimate_chat_tokens
from app.budget.service import TokenBudgetService
from app.core.audit import write_audit
from app.core.limits import ConcurrencyLimiter, get_ai_limiter
from app.core.security import RequestContext, get_request_context
from app.runtimeconfig.deps import get_runtime_settings
from app.runtimeconfig.models import RuntimeSettings

logger = logging.getLogger(__name__)

router = APIRouter()


class ChatRequest(BaseModel):
    """Input payload for agent conversational turns."""

    model_config = ConfigDict(extra="forbid")

    message: str = Field(
        min_length=1,
        max_length=1000,
        description="Customer natural language message",
    )

    @field_validator("message")
    @classmethod
    def validate_message_not_whitespace(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("Mesaj metni boş veya yalnızca boşluklardan oluşamaz.")
        return stripped


class PendingActionResponse(BaseModel):
    """Payload representing an action awaiting customer confirmation."""

    model_config = ConfigDict(frozen=True)

    action_id: str
    action_type: ActionType
    summary: str
    expires_at: datetime


class ChatResponse(BaseModel):
    """Unified response payload returned to the customer client."""

    model_config = ConfigDict(frozen=True)

    kind: ReplyKind
    reply: str
    citations: list[CitationResponse] = Field(default_factory=list)
    pending_action: PendingActionResponse | None = None


class ActionResultResponse(BaseModel):
    """Response payload for action confirmation or rejection."""

    model_config = ConfigDict(frozen=True)

    status: Literal["executed", "failed", "rejected"]
    message: str


@router.post("", response_model=ChatResponse)
@router.post("/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    req: Request,
    ctx: RequestContext = Depends(get_request_context),  # -> Gateway'in X-User-Id başlığını doğrular ve kullanıcı kimlik bağlamını üretir
    limiter: ConcurrencyLimiter = Depends(get_ai_limiter),  # -> Eşzamanlı istek kotasını (concurrency slot) kontrol eden sınırlayıcıyı çözer
    budget: TokenBudgetService | None = Depends(get_token_budget),  # -> Kullanıcının günlük/dakikalık LLM token bütçesini yöneten servisi çözer
    runtime: RuntimeSettings = Depends(get_runtime_settings),  # -> Spring Cloud Config Server dinamik runtime konfigürasyon snapshot'ını çözer
) -> ChatResponse:
    """Execute conversational turn with customer support agent."""
    service: AgentService | None = getattr(req.app.state, "agent_service", None)
    if service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Asistan servisi yapılandırılmamış veya erişilemiyor.",
        )

    try:
        # 1. Eşzamanlılık sınırı (ConcurrencyLimiter): Slot doluysa fast-fail 503
        async with limiter.slot():
            # 2. Token Bütçesi (Reserve & Reconcile): Bütçe aktifse peşin rezerve et
            if budget is not None:
                tokenizer = getattr(getattr(req.app.state, "rag_answer_service", None), "tokenizer", None)
                estimated_tokens = estimate_chat_tokens(
                    request.message,
                    tokenizer,
                    overhead=runtime.budget.prompt_overhead,
                    max_output=runtime.agent.max_output_tokens,
                    steps=min(2, max(1, runtime.agent.max_steps)),
                )

                async with await budget.reserve(
                    ctx.user_id,
                    estimated_tokens,
                    daily_limit=runtime.budget.daily_limit,
                    per_minute_limit=runtime.budget.per_minute_limit,
                    provider_tpm_limit=runtime.budget.provider_tpm_limit,
                ) as reservation:
                    # 3. Tur zaman aşımı (Turn Timeout): En fazla runtime.agent.turn_timeout_sec
                    async with asyncio.timeout(runtime.agent.turn_timeout_sec):
                        reply = await service.chat(request.message, ctx, limits=runtime.agent)
                        reservation.record(reply.usage)
            else:
                async with asyncio.timeout(runtime.agent.turn_timeout_sec):
                    reply = await service.chat(request.message, ctx, limits=runtime.agent)
    except (asyncio.TimeoutError, TimeoutError):
        # Kural: Loglara soru, mesaj veya kişisel veri ASLA yazılmaz! Yalnızca timeout durumu loglanır.
        logger.warning(
            "Agent chat turn zaman aşımına uğradı (limit: %.1fs)",
            runtime.agent.turn_timeout_sec,
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Cevap üretimi zaman aşımına uğradı.",
        )
    except (HTTPException, StarletteHTTPException):
        # Overloaded (503) gibi HTTP istisnalarını değiştirmeden yukarı fırlat
        raise
    except Exception as exc:
        logger.exception("Agent chat turn failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Cevap üretilirken bir hata oluştu.",
        )

    pending_resp = None
    if reply.pending_action:
        pending_resp = PendingActionResponse(
            action_id=reply.pending_action.action_id,
            action_type=reply.pending_action.action_type,
            summary=reply.pending_action.summary,
            expires_at=reply.pending_action.expires_at,
        )

    return ChatResponse(
        kind=reply.kind,
        reply=reply.reply,
        citations=reply.citations,
        pending_action=pending_resp,
    )


# ==============================================================================
# HASSAS İŞLEM (ACTION) ONAYLAMA VE REDDETME UÇ NOKTALARI
# ==============================================================================

@router.post("/actions/{action_id}/confirm", response_model=ActionResultResponse)
async def confirm_action(
    req: Request,
    action_id: str = Path(pattern=r"^[A-Za-z0-9_\-]{16,64}$"),
    ctx: RequestContext = Depends(get_request_context),  # -> Onaylayan kullanıcının kimliğini (user_id) doğrular; IDOR koruması sağlar
) -> ActionResultResponse:
    """Bekleyen hassas işlemi (Human-in-the-Loop) onaylar ve yürütür.

    Güvenlik ve Audit Kuralları:
    1. Tek Kullanımlık Token Tüketimi (One-Time Consume):
       `store.consume(action_id, ctx.user_id)` atomik olarak aksiyonu hafızadan silip döner.
       Böylece aynı onay linki ikinci kez kullanılamaz (Replay Attack koruması).
    2. Sahiplik İzolasyonu: Aksiyon ID'si geçerli olsa dahi oturum açan 'user_id' ile
       oluşturan kişi eşleşmiyorsa aksiyon bulunamaz (404 döner).
    3. Belirteç Hijyeni: 'action_id' tek kullanımlık bir yetki belirteci olduğu için
       audit loguna ASLA yazılmaz; yalnızca 'action_type' kaydedilir.
    """
    store: PendingActionStore | None = getattr(req.app.state, "action_store", None)
    executor: ActionExecutor | None = getattr(req.app.state, "action_executor", None)

    if store is None or executor is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="İşlem servisi yapılandırılmamış veya erişilemiyor.",
        )

    try:
        action = await asyncio.to_thread(store.consume, action_id, ctx.user_id)
    except PendingActionStoreError as exc:
        logger.exception("Pending action store consume failed: %s", exc)
        write_audit("action_confirm", user_id=ctx.user_id, correlation_id=ctx.correlation_id, outcome="unavailable")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="İşlem servisi geçici olarak kullanılamıyor, lütfen tekrar deneyin.",
        ) from exc
    if action is None:
        write_audit("action_confirm", user_id=ctx.user_id, correlation_id=ctx.correlation_id, outcome="not_found")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Bekleyen işlem bulunamadı ya da süresi doldu.",
        )

    try:
        exec_res = await executor.execute(action, ctx)
    except Exception as exc:
        logger.exception("Action execution failed: %s", exc)
        write_audit(
            "action_confirm",
            user_id=ctx.user_id,
            correlation_id=ctx.correlation_id,
            outcome="error",
            action_type=action.action_type,
        )
        restored = False
        try:
            if hasattr(store, "restore"):
                await asyncio.to_thread(store.restore, action)
            else:
                await asyncio.to_thread(store.create, action)
            restored = True
        except Exception as store_exc:
            logger.warning("Failed to restore action after execution failure: %s", store_exc)

        detail_msg = (
            "İşlem yürütülürken bir hata oluştu, lütfen kısa süre sonra tekrar deneyin."
            if restored
            else "İşlem yürütülemedi ve oturum kurtarılamadı. Lütfen talebinizi yeniden başlatın veya destek ile iletişime geçin."
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=detail_msg,
        ) from exc

    outcome = "executed" if exec_res.ok else "failed"
    write_audit(
        "action_confirm",
        user_id=ctx.user_id,
        correlation_id=ctx.correlation_id,
        outcome=outcome,
        action_type=action.action_type,
    )
    return ActionResultResponse(
        status="executed" if exec_res.ok else "failed",
        message=exec_res.message,
    )


@router.post("/actions/{action_id}/reject", response_model=ActionResultResponse)
async def reject_action(
    req: Request,
    action_id: str = Path(pattern=r"^[A-Za-z0-9_\-]{16,64}$"),
    ctx: RequestContext = Depends(get_request_context),  # -> Reddeden kullanıcının kimliğini (user_id) doğrular; IDOR koruması sağlar
) -> ActionResultResponse:
    """Explicitly reject/cancel a pending action."""
    store: PendingActionStore | None = getattr(req.app.state, "action_store", None)
    if store is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="İşlem servisi yapılandırılmamış veya erişilemiyor.",
        )

    try:
        discarded = await asyncio.to_thread(store.discard, action_id, ctx.user_id)
    except PendingActionStoreError as exc:
        logger.exception("Pending action store discard failed: %s", exc)
        write_audit("action_reject", user_id=ctx.user_id, correlation_id=ctx.correlation_id, outcome="unavailable")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="İşlem servisi geçici olarak kullanılamıyor, lütfen tekrar deneyin.",
        ) from exc
    if not discarded:
        write_audit("action_reject", user_id=ctx.user_id, correlation_id=ctx.correlation_id, outcome="not_found")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Bekleyen işlem bulunamadı ya da süresi doldu.",
        )

    write_audit("action_reject", user_id=ctx.user_id, correlation_id=ctx.correlation_id, outcome="rejected")
    return ActionResultResponse(
        status="rejected",
        message="İşlem iptal edildi.",
    )
