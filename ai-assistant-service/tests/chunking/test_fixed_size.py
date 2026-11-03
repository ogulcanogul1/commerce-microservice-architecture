import pytest
from app.rag.chunking.base import Chunker
from app.rag.chunking.strategies.fixed_size import FixedSizeChunker
from app.rag.chunking.models import ChunkingConfig
from app.rag.chunking.tokenizer import WhitespaceTokenizer
from app.rag.ingestion.models import Element, ElementType, ParsedDocument, QualityReport


@pytest.fixture
def sample_100_token_doc() -> ParsedDocument:
    # 100 kelimelik deterministik metin: "w000 w001 ... w099"
    words = [f"w{i:03d}" for i in range(100)]
    text = " ".join(words)
    elements = [
        Element(
            type=ElementType.PARAGRAPH,
            text=text,
            page_start=1,
            page_end=1,
            heading_path=["Genel"],
        )
    ]
    return ParsedDocument(
        source_file="doc_100.pdf",
        elements=elements,
        quality=QualityReport(page_count=1, status="ok"),
        parser_name="mock",
        parser_version="1.0",
    )


def test_fixed_size_chunker_protocol_conformance():
    tokenizer = WhitespaceTokenizer()
    config = ChunkingConfig()
    chunker = FixedSizeChunker(tokenizer, config)
    assert isinstance(chunker, Chunker)
    assert chunker.name == "fixed"


def test_fixed_size_empty_document():
    tokenizer = WhitespaceTokenizer()
    config = ChunkingConfig()
    chunker = FixedSizeChunker(tokenizer, config)

    doc = ParsedDocument(
        source_file="empty.pdf",
        elements=[],
        quality=QualityReport(page_count=0, status="ok"),
        parser_name="mock",
        parser_version="1.0",
    )
    chunks = chunker.chunk(doc)
    assert chunks == []


def test_fixed_size_sliding_window_100_tokens(sample_100_token_doc):
    tokenizer = WhitespaceTokenizer()
    # max=30, overlap=10, min=10 -> step=20
    # Pencereler: [0, 30), [20, 50), [40, 70), [60, 90), [80, 100)
    config = ChunkingConfig(max_tokens=30, overlap_tokens=10, min_tokens=10, include_breadcrumb=False)
    chunker = FixedSizeChunker(tokenizer, config)

    chunks = chunker.chunk(sample_100_token_doc)
    assert len(chunks) == 5

    # Her chunk'ın token sayısı <= 30
    for chunk in chunks:
        assert chunk.token_count <= 30
        assert chunk.strategy == "fixed"
        assert chunk.source_file == "doc_100.pdf"

    # İlk ve son chunk indeksleri ve token sayıları
    assert chunks[0].chunk_index == 0
    assert chunks[0].token_count == 30
    assert chunks[0].text.startswith("w000")
    assert chunks[0].text.endswith("w029")

    assert chunks[4].chunk_index == 4
    assert chunks[4].token_count == 20  # [80:100] arası 20 token
    assert chunks[4].text.startswith("w080")
    assert chunks[4].text.endswith("w099")

    # Ardışık chunk'lar tam 10 token paylaşıyor (overlap)
    for i in range(len(chunks) - 1):
        words_curr = chunks[i].text.split()
        words_next = chunks[i + 1].text.split()
        shared_curr = words_curr[-10:]
        shared_next = words_next[:10]
        assert shared_curr == shared_next, f"Overlap mismatch at index {i}"

    # Kapsama (coverage): Orijinal metnin tüm kelimeleri en az bir chunk'ta var
    covered_words = set()
    for chunk in chunks:
        covered_words.update(chunk.text.split())
    assert len(covered_words) == 100


def test_fixed_size_no_overlap_only_tail():
    """Kalan token sayısı overlap payından küçük veya eşitse ekstra gereksiz chunk açılmamalı."""
    tokenizer = WhitespaceTokenizer()
    # 35 kelimelik doküman: max=30, overlap=10 -> step=20
    # 1. chunk: [0:30]
    # Kalan: 5 token (<= 10 overlap). 2. chunk açılmamalı çünkü bu 5 token zaten 1. chunk'ın içinde yoktu ama
    # burada 30 token alındı, kalan 5 token yeni bir pencere oluşturursa [20:35] olur (15 token).
    # Ancak eğer doküman 32 kelime olsa ve max=30, overlap=10 olsa:
    # 1. pencere: [0:30]
    # İkinci pencere başlangıcı: i = 20. Kalan token = 32 - 20 = 12 (> 10) -> açılır.
    # Eğer doküman 25 kelime olsa:
    # 1. pencere: [0:25]. i=20'ye geçer, kalan 25 - 20 = 5 (<= 10) -> açılmaz!
    words = [f"word{i}" for i in range(25)]
    doc = ParsedDocument(
        source_file="short.pdf",
        elements=[
            Element(
                type=ElementType.PARAGRAPH,
                text=" ".join(words),
                page_start=1,
                page_end=1,
            )
        ],
        quality=QualityReport(page_count=1, status="ok"),
        parser_name="mock",
        parser_version="1.0",
    )
    config = ChunkingConfig(max_tokens=30, overlap_tokens=10, min_tokens=10, include_breadcrumb=False)
    chunker = FixedSizeChunker(tokenizer, config)

    chunks = chunker.chunk(doc)
    assert len(chunks) == 1
    assert chunks[0].token_count == 25


def test_fixed_size_deterministic_ids():
    tokenizer = WhitespaceTokenizer()
    config1 = ChunkingConfig(max_tokens=20, overlap_tokens=5, min_tokens=5)
    config2 = ChunkingConfig(max_tokens=40, overlap_tokens=10, min_tokens=10)

    doc = ParsedDocument(
        source_file="sample.pdf",
        elements=[
            Element(
                type=ElementType.PARAGRAPH,
                text="Aynı girdi iki kez çalıştırıldığında aynı id'leri ve metinleri üretmelidir.",
                page_start=1,
                page_end=1,
            )
        ],
        quality=QualityReport(page_count=1, status="ok"),
        parser_name="mock",
        parser_version="1.0",
    )

    chunker1_a = FixedSizeChunker(tokenizer, config1)
    chunker1_b = FixedSizeChunker(tokenizer, config1)
    chunks_a = chunker1_a.chunk(doc)
    chunks_b = chunker1_b.chunk(doc)

    assert [c.id for c in chunks_a] == [c.id for c in chunks_b]

    # Config değişince ID'ler değişmeli
    chunker2 = FixedSizeChunker(tokenizer, config2)
    chunks2 = chunker2.chunk(doc)
    assert chunks_a[0].id != chunks2[0].id


def test_fixed_size_deducts_breadcrumb_budget():
    """include_breadcrumb=True olduğunda prefix token'ları bütçeden düşülmeli, embedding_text <= max_tokens kalmalıdır."""
    tokenizer = WhitespaceTokenizer()
    words = [f"w{i:03d}" for i in range(50)]
    elements = [
        Element(
            type=ElementType.PARAGRAPH,
            text=" ".join(words),
            page_start=1,
            page_end=1,
            heading_path=["Kategori", "Alt Kategori"],
        )
    ]
    doc = ParsedDocument(
        source_file="doc_bc.pdf",
        elements=elements,
        quality=QualityReport(page_count=1, status="ok"),
        parser_name="mock",
        parser_version="1.0",
    )

    config = ChunkingConfig(max_tokens=30, overlap_tokens=5, min_tokens=5, include_breadcrumb=True)
    chunker = FixedSizeChunker(tokenizer, config)
    chunks = chunker.chunk(doc)

    assert len(chunks) >= 2
    for c in chunks:
        # embedding_text toplam token sayısı <= 30 olmalıdır
        assert tokenizer.count(c.embedding_text) <= 30
        assert c.context_prefix == "Kategori > Alt Kategori"

