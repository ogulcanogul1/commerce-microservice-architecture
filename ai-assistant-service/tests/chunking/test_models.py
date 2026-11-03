import pytest
from pydantic import ValidationError

from app.rag.chunking.models import Chunk, ChunkingConfig, ChunkStrategy
from app.rag.ingestion.models import ElementType


def test_chunk_strategy_enum():
    assert ChunkStrategy.FIXED == "fixed"
    assert ChunkStrategy.RECURSIVE == "recursive"
    assert ChunkStrategy.STRUCTURE == "structure"
    assert str(ChunkStrategy.FIXED) == "fixed"


def test_chunking_config_defaults():
    config = ChunkingConfig()
    assert config.max_tokens == 300
    assert config.overlap_tokens == 45
    assert config.min_tokens == 60
    assert config.include_breadcrumb is True
    assert config.isolate_tables is False
    assert len(config.config_hash()) == 8


def test_chunking_config_hash_deterministic():
    c1 = ChunkingConfig(max_tokens=350, overlap_tokens=50)
    c2 = ChunkingConfig(max_tokens=350, overlap_tokens=50)
    c3 = ChunkingConfig(max_tokens=200, overlap_tokens=20)
    assert c1.config_hash() == c2.config_hash()
    assert c1.config_hash() != c3.config_hash()


def test_chunking_config_invalid_thresholds():
    with pytest.raises(ValidationError, match="overlap_tokens .* must be strictly less than max_tokens"):
        ChunkingConfig(max_tokens=100, overlap_tokens=100)

    with pytest.raises(ValidationError, match="min_tokens .* cannot be greater than max_tokens"):
        ChunkingConfig(max_tokens=100, overlap_tokens=20, min_tokens=150)


def test_chunk_embedding_text_with_and_without_prefix():
    chunk_with_prefix = Chunk(
        id="chunk-1",
        strategy="fixed",
        source_file="doc.pdf",
        chunk_index=0,
        text="Bu bir örnek metindir.",
        context_prefix="Bölüm 1 > Giriş",
        token_count=5,
        page_start=1,
        page_end=1,
        heading_path=["Bölüm 1", "Giriş"],
        element_types=[ElementType.PARAGRAPH],
        char_start=0,
        char_end=23,
    )
    assert chunk_with_prefix.embedding_text == "Bölüm 1 > Giriş\n\nBu bir örnek metindir."

    chunk_without_prefix = Chunk(
        id="chunk-2",
        strategy="fixed",
        source_file="doc.pdf",
        chunk_index=1,
        text="Öneksiz metin.",
        context_prefix="",
        token_count=3,
        page_start=1,
        page_end=1,
        char_start=24,
        char_end=38,
    )
    assert chunk_without_prefix.embedding_text == "Öneksiz metin."


def test_chunk_validation_empty_text():
    with pytest.raises(ValidationError, match="Chunk text cannot be empty"):
        Chunk(
            id="c-empty",
            strategy="fixed",
            source_file="doc.pdf",
            chunk_index=0,
            text="   ",
            token_count=0,
            page_start=1,
            page_end=1,
            char_start=0,
            char_end=0,
        )


def test_chunk_validation_invalid_page_range():
    with pytest.raises(ValidationError, match="page_end .* cannot be less than page_start"):
        Chunk(
            id="c-page",
            strategy="fixed",
            source_file="doc.pdf",
            chunk_index=0,
            text="Metin",
            token_count=1,
            page_start=2,
            page_end=1,
            char_start=0,
            char_end=5,
        )


def test_chunk_validation_invalid_char_range():
    with pytest.raises(ValidationError, match="char_end .* cannot be less than char_start"):
        Chunk(
            id="c-char",
            strategy="fixed",
            source_file="doc.pdf",
            chunk_index=0,
            text="Metin",
            token_count=1,
            page_start=1,
            page_end=1,
            char_start=10,
            char_end=5,
        )
