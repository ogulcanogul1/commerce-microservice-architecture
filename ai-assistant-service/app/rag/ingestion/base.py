from pathlib import Path
from typing import Protocol, runtime_checkable

from app.rag.ingestion.models import ParsedDocument


@runtime_checkable
class DocumentLoader(Protocol):
    """Protocol defining the interface for all document loaders (PDF, DOCX, HTML, etc.).""" 

    def load(self,path:Path) -> ParsedDocument:
        """Parse a document from a file path and return a ParsedDocument."""
        pass