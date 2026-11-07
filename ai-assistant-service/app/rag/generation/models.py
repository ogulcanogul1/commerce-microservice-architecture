"""Data models for RAG generation, context building, citations, and validation."""

from __future__ import annotations

from typing import Any, Literal
from pydantic import BaseModel, Field

from app.llm.base import TokenUsage
from app.rag.chunking.models import Chunk
from app.rag.vectorstore.models import SearchHit

AbstainReason = Literal[
    "no_results",
    "low_retrieval_score",
    "model_abstained",
    "validation_failed",
]

IssueType = Literal[
    "uncited_sentence",
    "invalid_citation",
    "number_not_in_source",
    "empty_answer",
]


class GenerationConfig(BaseModel):
    """Configuration for RAG answer generation, validation, and context budget."""

    top_k: int = Field(default=5, ge=1, le=20)
    context_token_budget: int = Field(default=1500, ge=100)
    min_dense_score: float | None = None
    max_attempts: int = Field(default=2, ge=1, le=3)
    temperature: float = Field(default=0.0, ge=0.0, le=1.0)
    max_output_tokens: int = Field(default=400, ge=50)
    llm_timeout_sec: float = Field(default=30.0, gt=0)
    abstain_message: str = (
        "Bu konuda dokümanlarımızda bilgi bulamadım. Sizi bir müşteri temsilcisine yönlendirebilirim."
    )
    retrieval_mode: Literal["dense", "sparse", "hybrid"] = "hybrid"

    # Reranker Configuration
    rerank_enabled: bool = False
    rerank_candidates: int = Field(default=20, ge=1, le=50)
    rerank_fail_open: bool = True

    model_config = {"frozen": True}

    @classmethod
    def from_settings(cls, settings: Any) -> GenerationConfig:
        """Create a GenerationConfig instance mapped from application Settings."""
        return cls(
            top_k=settings.RAG_TOP_K,
            context_token_budget=settings.RAG_CONTEXT_TOKEN_BUDGET,
            min_dense_score=settings.RAG_MIN_DENSE_SCORE,
            max_attempts=settings.RAG_MAX_ATTEMPTS,
            temperature=settings.RAG_TEMPERATURE,
            max_output_tokens=settings.RAG_MAX_OUTPUT_TOKENS,
            llm_timeout_sec=settings.RAG_LLM_TIMEOUT_SEC,
            abstain_message=settings.RAG_ABSTAIN_MESSAGE,
            retrieval_mode=getattr(settings, "RAG_RETRIEVAL_MODE", "hybrid"),
            rerank_enabled=getattr(settings, "RAG_RERANK_ENABLED", False),
            rerank_candidates=getattr(settings, "RAG_RERANK_CANDIDATES", 20),
            rerank_fail_open=getattr(settings, "RAG_RERANK_FAIL_OPEN", True),
        )


class RetrievalOutcome(BaseModel):
    """Retrieval aşamasının (rerank dahil) tüm çıktısını ve telemetrisini temsil eden model."""

    hits: list[SearchHit] = Field(default_factory=list, description="Nihai arama eşleşmeleri")
    top_dense_score: float | None = Field(default=None, description="En iyi dense cosine benzerlik skoru")
    rerank_status: Literal["disabled", "ok", "failed"] = Field(
        default="disabled", description="Reranker işlem durumu"
    )
    rerank_candidates: int = Field(default=0, description="Reranker'a gönderilen aday sayısı")
    rerank_ms: float = Field(default=0.0, description="Rerank aşamasında harcanan süre (ms)")

    model_config = {"frozen": True}


class ContextBlock(BaseModel):
    """A numbered reference block included in the LLM generation prompt context."""

    number: int = Field(description="1-based sequential reference number matching [n] citations")
    chunk: Chunk = Field(description="Underlying document chunk")
    header: str = Field(description="Formatted citation header line e.g. [1] (iade.pdf, s. 1–2, İade > Süre)")
    token_count: int = Field(description="Combined token count of header and text")

    model_config = {"frozen": True}


class Citation(BaseModel):
    """Verified citation pointing to a specific source chunk."""

    number: int = Field(description="Sequential number referenced in the generated answer")
    chunk_id: str = Field(description="Server-side persistent chunk UUID/hex identifier")
    source_file: str = Field(description="Name of the source document")
    page_start: int = Field(description="Starting page number")
    page_end: int = Field(description="Ending page number")
    heading_path: list[str] = Field(default_factory=list, description="Section hierarchy path")

    model_config = {"frozen": True}


class ValidationIssue(BaseModel):
    """Diagnostics detail of a failed citation or grounding check."""

    type: IssueType = Field(description="Specific validation rule violated")
    sentence: str = Field(description="The sentence in the answer that produced the issue")
    detail: str = Field(default="", description="Specific token, number or citation detail (e.g. '30' or '[4]')")

    model_config = {"frozen": True}


class RagAnswer(BaseModel):
    """Complete generation outcome envelope containing answer, citations, and telemetry."""

    status: Literal["answered", "abstained"] = Field(description="Final outcome status of the generation")
    answer: str = Field(description="Generated natural language response or abstain fallback message")
    abstain_reason: AbstainReason | None = Field(default=None, description="Explicit reason if abstained")
    citations: list[Citation] = Field(default_factory=list, description="List of verified citations actually used")
    attempts: int = Field(default=0, description="Total LLM generation iterations executed")
    top_dense_score: float | None = Field(default=None, description="Best dense retrieval cosine score")
    retrieved_chunk_ids: list[str] = Field(default_factory=list, description="All chunk IDs retrieved from vector store")
    context_chunk_ids: list[str] = Field(default_factory=list, description="Chunk IDs selected within context budget")
    validation_issues: list[ValidationIssue] = Field(default_factory=list, description="Validation issues from last attempt")
    usage: TokenUsage = Field(default_factory=TokenUsage, description="Aggregated token usage across all attempts")
    provider: str | None = Field(default=None, description="LLM provider name utilized")
    model: str | None = Field(default=None, description="Specific LLM model utilized")
    rerank_status: Literal["disabled", "ok", "failed"] = Field(
        default="disabled", description="Reranker invocation outcome status"
    )
