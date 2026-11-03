from typing import Protocol, runtime_checkable
from app.rag.chunking.models import Chunk
from app.rag.ingestion.models import ParsedDocument


@runtime_checkable
class Chunker(Protocol):
    """Unified protocol that all chunking implementations must satisfy."""

    name: str

    def chunk(self, doc: ParsedDocument) -> list[Chunk]:
        """Split a ParsedDocument into a sequence of Chunk objects."""
        ...
