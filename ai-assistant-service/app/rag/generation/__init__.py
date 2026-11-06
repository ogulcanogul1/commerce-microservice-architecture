"""Generation package for RAG answer generation, citation checking, and validation."""

from app.rag.generation.citations import (
    ABBREVIATIONS,
    cited_numbers,
    extract_citation_numbers,
    is_abstain,
    split_sentences,
    validate_answer,
)
from app.rag.generation.context import build_context
from app.rag.generation.models import (
    AbstainReason,
    Citation,
    ContextBlock,
    GenerationConfig,
    IssueType,
    RagAnswer,
    ValidationIssue,
)
from app.rag.generation.prompt import (
    ABSTAIN_MARKER,
    SYSTEM_PROMPT,
    build_messages,
    build_retry_messages,
)

__all__ = [
    "AbstainReason",
    "IssueType",
    "GenerationConfig",
    "ContextBlock",
    "Citation",
    "ValidationIssue",
    "RagAnswer",
    "build_context",
    "ABSTAIN_MARKER",
    "SYSTEM_PROMPT",
    "build_messages",
    "build_retry_messages",
    "split_sentences",
    "extract_citation_numbers",
    "cited_numbers",
    "is_abstain",
    "validate_answer",
    "ABBREVIATIONS",
]
