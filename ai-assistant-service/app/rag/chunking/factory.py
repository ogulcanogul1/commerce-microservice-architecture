from typing import Union
from app.rag.chunking.base import Chunker
from app.rag.chunking.models import ChunkingConfig, ChunkStrategy
from app.rag.chunking.strategies.fixed_size import FixedSizeChunker
from app.rag.chunking.strategies.recursive import RecursiveChunker
from app.rag.chunking.strategies.structure_aware import StructureAwareChunker
from app.rag.chunking.tokenizer import Tokenizer


def get_chunker(
    strategy: Union[str, ChunkStrategy],
    tokenizer: Tokenizer,
    config: ChunkingConfig,
) -> Chunker:
    """Factory function to instantiate chunkers based on strategy name or enum."""
    try:
        strat = ChunkStrategy(strategy)
    except ValueError:
        valid_strategies = [s.value for s in ChunkStrategy]
        raise ValueError(
            f"Unknown chunking strategy '{strategy}'. Valid strategies are: {valid_strategies}"
        )

    if strat == ChunkStrategy.FIXED:
        return FixedSizeChunker(tokenizer, config)
    elif strat == ChunkStrategy.RECURSIVE:
        return RecursiveChunker(tokenizer, config)
    elif strat == ChunkStrategy.STRUCTURE:
        return StructureAwareChunker(tokenizer, config)
    else:
        raise ValueError(f"Unhandled chunking strategy '{strat}'.")
