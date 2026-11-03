from app.rag.chunking.base import Chunker
from app.rag.chunking.models import Chunk, ChunkingConfig, ChunkStrategy
from app.rag.chunking.tokenizer import Tokenizer, WhitespaceTokenizer, TiktokenTokenizer
from app.rag.chunking.flatten import FlatDocument, Span, flatten
from app.rag.chunking.factory import get_chunker
from app.rag.chunking.strategies import (
    FixedSizeChunker,
    RecursiveChunker,
    StructureAwareChunker,
)

# E-ticaret belgelerindeki yoğun tablo ve başlık hiyerarşisi nedeniyle varsayılan chunker
DefaultChunker = StructureAwareChunker

__all__ = [
    "Chunker",
    "Chunk",
    "ChunkingConfig",
    "ChunkStrategy",
    "Tokenizer",
    "WhitespaceTokenizer",
    "TiktokenTokenizer",
    "FlatDocument",
    "Span",
    "flatten",
    "get_chunker",
    "FixedSizeChunker",
    "RecursiveChunker",
    "StructureAwareChunker",
    "DefaultChunker",
]
