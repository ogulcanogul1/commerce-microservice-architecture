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
from app.core.config import settings
from app.core.limits import ConcurrencyLimiter, get_ai_limiter
from app.core.security import RequestContext, get_request_context

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
    ctx: RequestContext = Depends(get_request_context),
    limiter: ConcurrencyLimiter = Depends(get_ai_limiter),
    budget: TokenBudgetService | None = Depends(get_token_budget),
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
                    overhead=settings.TOKEN_BUDGET_PROMPT_OVERHEAD,
                    max_output=settings.AGENT_MAX_OUTPUT_TOKENS,
                    steps=min(2, max(1, settings.AGENT_MAX_STEPS)),
                )
                async with await budget.reserve(ctx.user_id, estimated_tokens) as reservation:
                    # 3. Tur zaman aşımı (Turn Timeout): En fazla 60 sn
                    async with asyncio.timeout(settings.AGENT_TURN_TIMEOUT_SEC):
                        reply = await service.chat(request.message, ctx)
                        reservation.record(reply.usage)
            else:
                async with asyncio.timeout(settings.AGENT_TURN_TIMEOUT_SEC):
                    reply = await service.chat(request.message, ctx)
    except (asyncio.TimeoutError, TimeoutError):
        # Kural: Loglara soru, mesaj veya kişisel veri ASLA yazılmaz! Yalnızca timeout durumu loglanır.
        logger.warning(
            "Agent chat turn zaman aşımına uğradı (limit: %.1fs)",
            settings.AGENT_TURN_TIMEOUT_SEC,
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


@router.post("/actions/{action_id}/confirm", response_model=ActionResultResponse)
async def confirm_action(
    req: Request,
    action_id: str = Path(pattern=r"^[A-Za-z0-9_\-]{16,64}$"),
    ctx: RequestContext = Depends(get_request_context),
) -> ActionResultResponse:
    """Confirm and execute a pending sensitive action."""
    store: PendingActionStore | None = getattr(req.app.state, "action_store", None)
    executor: ActionExecutor | None = getattr(req.app.state, "action_executor", None)

    if store is None or executor is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="İşlem servisi yapılandırılmamış veya erişilemiyor.",
        )

    try:
        action = store.consume(action_id, ctx.user_id)
    except PendingActionStoreError as exc:
        logger.exception("Pending action store consume failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="İşlem servisi geçici olarak kullanılamıyor, lütfen tekrar deneyin.",
        ) from exc
    if action is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Bekleyen işlem bulunamadı ya da süresi doldu.",
        )

    try:
        exec_res = await executor.execute(action, ctx)
    except Exception as exc:
        logger.exception("Action execution failed: %s", exc)
        restored = False
        try:
            if hasattr(store, "restore"):
                store.restore(action)
            else:
                store.create(action)
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

    return ActionResultResponse(
        status="executed" if exec_res.ok else "failed",
        message=exec_res.message,
    )


@router.post("/actions/{action_id}/reject", response_model=ActionResultResponse)
async def reject_action(
    req: Request,
    action_id: str = Path(pattern=r"^[A-Za-z0-9_\-]{16,64}$"),
    ctx: RequestContext = Depends(get_request_context),
) -> ActionResultResponse:
    """Explicitly reject/cancel a pending action."""
    store: PendingActionStore | None = getattr(req.app.state, "action_store", None)
    if store is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="İşlem servisi yapılandırılmamış veya erişilemiyor.",
        )

    try:
        discarded = store.discard(action_id, ctx.user_id)
    except PendingActionStoreError as exc:
        logger.exception("Pending action store discard failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="İşlem servisi geçici olarak kullanılamıyor, lütfen tekrar deneyin.",
        ) from exc
    if not discarded:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Bekleyen işlem bulunamadı ya da süresi doldu.",
        )

    return ActionResultResponse(
        status="rejected",
        message="İşlem iptal edildi.",
    )
