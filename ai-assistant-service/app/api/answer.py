"""API endpoint for RAG question-answering (POST /rag/answer)."""

from __future__ import annotations

import asyncio
import logging
from typing import Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from pydantic import BaseModel, Field, field_validator
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.budget.deps import get_budget_subject, get_token_budget
from app.budget.estimator import estimate_chat_tokens
from app.budget.service import TokenBudgetService
from app.core.config import settings
from app.core.limits import ConcurrencyLimiter, get_ai_limiter
from app.rag.generation.models import AbstainReason, RagAnswer
from app.rag.generation.service import RagAnswerService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["RAG Answer"])


class AnswerRequest(BaseModel):
    """Input payload for RAG question answering."""

    question: str = Field(
        min_length=1,
        max_length=1000,
        description="User query in natural language",
    )
    k: int | None = Field(
        default=None,
        ge=1,
        le=10,
        description="Number of candidate chunks to retrieve (None falls back to config.top_k)",
    )
    source_file: str | None = Field(
        default=None,
        description="Optional filter targeting a specific document source file",
    )

    @field_validator("question")
    @classmethod
    def validate_question_not_whitespace(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("Soru metni boş veya yalnızca boşluklardan oluşamaz.")
        return stripped


class CitationResponse(BaseModel):
    """External citation payload referencing verified source grounding."""

    number: int = Field(description="Sequential citation number [n] used in answer")
    chunk_id: str = Field(description="Unique persistent chunk identifier")
    source_file: str = Field(description="Source document filename")
    page_start: int = Field(description="Starting page number")
    page_end: int = Field(description="Ending page number")
    heading_path: list[str] = Field(default_factory=list, description="Section hierarchy path")


class AnswerResponse(BaseModel):
    """Public answer response envelope excluding internal diagnostics."""

    status: Literal["answered", "abstained"] = Field(
        description="Whether the query was answered or abstained"
    )
    answer: str = Field(description="Generated natural language response or corporate fallback message")
    abstain_reason: AbstainReason | None = Field(
        default=None,
        description="Reason code if abstained (None if answered)",
    )
    citations: list[CitationResponse] = Field(
        default_factory=list,
        description="List of verified citations actually referenced in the answer",
    )


def get_rag_answer_service(request: Request) -> RagAnswerService:
    """Dependency resolver obtaining the initialized RagAnswerService from FastAPI app state."""
    service = getattr(request.app.state, "rag_answer_service", None)
    if service is None:
        logger.error("RagAnswerService app.state üzerinde bulunamadı.")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Cevap üretimi servisi yapılandırılmamış veya erişilemiyor.",
        )
    return service


@router.post(
    "/rag/answer",
    response_model=AnswerResponse,
    summary="Dokümanlara dayalı kaynaklı cevap üretir",
    description=(
        "Kullanıcı sorusunu PII maskelemesinden geçirir, Qdrant üzerinden en alakalı "
        "parçaları getirir, token bütçesine göre prompt oluşturur, LLM ile yanıt üretir "
        "ve atıfları kod seviyesinde doğrulayarak döner."
    ),
    responses={
        200: {"description": "Cevap başarıyla üretildi veya kurumsal mesajla abstain edildi."},
        422: {"description": "Geçersiz istek (boş soru, aşırı uzunluk, limit aşımı)."},
        503: {"description": "Koleksiyon henüz indekslenmemiş, LLM zaman aşımı veya servis kesintisi."},
    },
)
async def answer_question(
    payload: AnswerRequest,
    service: RagAnswerService = Depends(get_rag_answer_service),
    x_correlation_id: str | None = Header(default=None, alias="X-Correlation-Id"),
    limiter: ConcurrencyLimiter = Depends(get_ai_limiter),
    subject: str = Depends(get_budget_subject),
    budget: TokenBudgetService | None = Depends(get_token_budget),
) -> AnswerResponse:
    """Execute end-to-end grounded RAG question answering."""
    try:
        # 1. Eşzamanlılık sınırı (ConcurrencyLimiter): Slot doluysa fast-fail 503
        async with limiter.slot():
            # 2. Token Bütçesi (Reserve & Reconcile): Bütçe aktifse peşin rezerve et
            if budget is not None:
                estimated_tokens = estimate_chat_tokens(
                    payload.question,
                    service.tokenizer,
                    overhead=settings.TOKEN_BUDGET_PROMPT_OVERHEAD,
                    max_output=settings.RAG_MAX_OUTPUT_TOKENS,
                    steps=1,
                )
                async with await budget.reserve(subject, estimated_tokens) as reservation:
                    # 3. RAG tur zaman aşımı: En fazla 45 sn
                    async with asyncio.timeout(settings.RAG_TURN_TIMEOUT_SEC):
                        rag_answer: RagAnswer = await service.answer(
                            payload.question,
                            k=payload.k,
                            source_file=payload.source_file,
                            correlation_id=x_correlation_id,
                        )
                        reservation.record(rag_answer.usage)
            else:
                async with asyncio.timeout(settings.RAG_TURN_TIMEOUT_SEC):
                    rag_answer: RagAnswer = await service.answer(
                        payload.question,
                        k=payload.k,
                        source_file=payload.source_file,
                        correlation_id=x_correlation_id,
                    )
    except (asyncio.TimeoutError, TimeoutError):
        # Kural: Loglara kullanıcı sorusu veya metin ASLA yazılmaz! Yalnızca timeout durumu loglanır.
        logger.warning(
            "RAG Answer üretimi zaman aşımına uğradı (limit: %.1fs)",
            settings.RAG_TURN_TIMEOUT_SEC,
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Cevap üretimi zaman aşımına uğradı.",
        ) from None
    except RuntimeError as exc:
        msg = str(exc)
        if "henüz indekslenmemiş" in msg:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Vektör koleksiyonu henüz indekslenmemiş.",
            ) from None
        logger.error("RAG Answer üretiminde RuntimeError: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Cevap üretilirken bir hata oluştu.",
        ) from None
    except (HTTPException, StarletteHTTPException):
        # Overloaded (503) gibi HTTP istisnalarını değiştirmeden yukarı fırlat
        raise
    except Exception as exc:
        logger.error("RAG Answer üretiminde beklenmeyen hata: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Cevap üretilirken bir hata oluştu.",
        ) from None

    # Map to public response envelope
    citations_response = [
        CitationResponse(
            number=c.number,
            chunk_id=c.chunk_id,
            source_file=c.source_file,
            page_start=c.page_start,
            page_end=c.page_end,
            heading_path=c.heading_path,
        )
        for c in rag_answer.citations
    ]

    return AnswerResponse(
        status=rag_answer.status,
        answer=rag_answer.answer,
        abstain_reason=rag_answer.abstain_reason,
        citations=citations_response,
    )
