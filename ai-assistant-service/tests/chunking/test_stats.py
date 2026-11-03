import pytest
from app.rag.chunking.models import Chunk, ChunkStrategy
from app.rag.chunking.tokenizer import WhitespaceTokenizer
from app.rag.evaluation.chunking.stats import chunk_stats, ChunkStats
from app.rag.ingestion.models import Element, ElementType, ParsedDocument, QualityReport


@pytest.fixture
def empty_doc() -> ParsedDocument:
    return ParsedDocument(
        source_file="empty.pdf",
        elements=[],
        quality=QualityReport(page_count=0, status="ok"),
        parser_name="mock",
        parser_version="1.0",
    )


def test_chunk_stats_empty(empty_doc):
    tokenizer = WhitespaceTokenizer()
    stats = chunk_stats([], empty_doc, tokenizer)

    assert stats.chunk_count == 0
    assert stats.tokens_mean == 0.0
    assert stats.redundancy == 1.0
    assert stats.sentence_cut_ratio == 0.0


def test_chunk_stats_token_distribution():
    tokenizer = WhitespaceTokenizer()
    doc = ParsedDocument(
        source_file="doc.pdf",
        elements=[Element(type=ElementType.PARAGRAPH, text="w " * 50, page_start=1, page_end=1)],
        quality=QualityReport(page_count=1, status="ok"),
        parser_name="mock",
        parser_version="1.0",
    )

    chunks = [
        Chunk(
            id="c1",
            strategy=ChunkStrategy.FIXED,
            source_file="doc.pdf",
            chunk_index=0,
            text="Metin bir.",
            token_count=10,
            page_start=1,
            page_end=1,
            char_start=0,
            char_end=10,
        ),
        Chunk(
            id="c2",
            strategy=ChunkStrategy.FIXED,
            source_file="doc.pdf",
            chunk_index=1,
            text="Metin iki.",
            token_count=30,
            page_start=1,
            page_end=1,
            char_start=10,
            char_end=20,
        ),
        Chunk(
            id="c3",
            strategy=ChunkStrategy.FIXED,
            source_file="doc.pdf",
            chunk_index=2,
            text="Metin üç.",
            token_count=50,
            page_start=1,
            page_end=1,
            char_start=20,
            char_end=30,
        ),
    ]

    stats = chunk_stats(chunks, doc, tokenizer, min_tokens=20)
    assert stats.chunk_count == 3
    assert stats.tokens_min == 10
    assert stats.tokens_max == 50
    assert stats.tokens_mean == 30.0
    assert stats.tokens_p50 == 30.0
    assert stats.under_min_ratio == round(1 / 3, 4)  # Sadece c1 (10 token) < 20


def test_chunk_stats_sentence_cut_detection(empty_doc):
    tokenizer = WhitespaceTokenizer()

    chunks = [
        # Düzgün biten ve başlayan chunk
        Chunk(
            id="c1",
            strategy=ChunkStrategy.RECURSIVE,
            source_file="d.pdf",
            chunk_index=0,
            text="Bu düzgün bir cümledir.",
            token_count=4,
            page_start=1,
            page_end=1,
            char_start=0,
            char_end=24,
        ),
        # Küçük harfle başlayan (kesilmiş) chunk
        Chunk(
            id="c2",
            strategy=ChunkStrategy.FIXED,
            source_file="d.pdf",
            chunk_index=1,
            text="ile devam eden ve noktasız biten",
            token_count=6,
            page_start=1,
            page_end=1,
            char_start=25,
            char_end=57,
        ),
    ]

    stats = chunk_stats(chunks, empty_doc, tokenizer)
    # c1 düzgün, c2 hem küçükle başlıyor hem noktasız bitiyor -> 1 / 2 = 0.5
    assert stats.sentence_cut_ratio == 0.5


def test_chunk_stats_table_split_and_headless_detection():
    tokenizer = WhitespaceTokenizer()
    table_text = "| A | B |\n|---|---|\n| 1 | 2 |\n| 3 | 4 |"
    doc = ParsedDocument(
        source_file="d.pdf",
        elements=[
            Element(type=ElementType.TABLE, text=table_text, page_start=1, page_end=1)
        ],
        quality=QualityReport(page_count=1, status="ok"),
        parser_name="mock",
        parser_version="1.0",
    )

    chunks = [
        # Tablonun başlığını içeren ilk parça
        Chunk(
            id="c1",
            strategy=ChunkStrategy.STRUCTURE,
            source_file="d.pdf",
            chunk_index=0,
            text="| A | B |\n|---|---|\n| 1 | 2 |",
            token_count=10,
            page_start=1,
            page_end=1,
            element_types=[ElementType.TABLE],
            char_start=0,
            char_end=30,
        ),
        # Başlığı olmayan ham satırlardan oluşan ikinci parça (Fixed-size senaryosu)
        Chunk(
            id="c2",
            strategy=ChunkStrategy.FIXED,
            source_file="d.pdf",
            chunk_index=1,
            text="| 3 | 4 |\n| 5 | 6 |",
            token_count=8,
            page_start=1,
            page_end=1,
            element_types=[ElementType.TABLE],
            char_start=30,
            char_end=50,
        ),
    ]

    stats = chunk_stats(chunks, doc, tokenizer)
    # 1 adet tablo var, 2 parçaya ayrılmış -> split_ratio = 1.0
    assert stats.table_split_ratio == 1.0
    # c2'de |---| ayırıcısı olmadığı için 1 adet headless chunk tespit edilmeli
    assert stats.table_headless_chunks == 1


def test_chunk_stats_orphan_heading_detection(empty_doc):
    tokenizer = WhitespaceTokenizer()

    chunks = [
        # Son satırı başlık olan chunk (arkasından içerik gelmiyor)
        Chunk(
            id="c1",
            strategy=ChunkStrategy.FIXED,
            source_file="d.pdf",
            chunk_index=0,
            text="Paragraf metni bitti.\n\nİkinci Bölüm Başlığı",
            token_count=6,
            page_start=1,
            page_end=1,
            char_start=0,
            char_end=42,
        ),
        # Normal chunk
        Chunk(
            id="c2",
            strategy=ChunkStrategy.RECURSIVE,
            source_file="d.pdf",
            chunk_index=1,
            text="Bu bölümün devamı burada yer alıyor.",
            token_count=6,
            page_start=1,
            page_end=1,
            char_start=43,
            char_end=80,
        ),
    ]

    stats = chunk_stats(chunks, empty_doc, tokenizer)
    # c1 orphan heading içeriyor -> 1 / 2 = 0.5
    assert stats.orphan_heading_ratio == 0.5
