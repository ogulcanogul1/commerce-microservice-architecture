"""Generation package for RAG answer generation, citation checking, and validation."""

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

__all__ = [
    "AbstainReason",
    "IssueType",
    "GenerationConfig",
    "ContextBlock",
    "Citation",
    "ValidationIssue",
    "RagAnswer",
    "build_context",
]
