import pytest
from app.rag.chunking.base import Chunker
from app.rag.chunking.factory import get_chunker
from app.rag.chunking.models import ChunkingConfig, ChunkStrategy
from app.rag.chunking.tokenizer import WhitespaceTokenizer
from app.rag.ingestion.models import Element, ElementType, ParsedDocument, QualityReport


@pytest.fixture
def rich_synthetic_document() -> ParsedDocument:
    """Başlık, paragraf, tablo ve liste içeren 3 sayfalık zengin sentetik doküman fixture'ı."""
    elements = [
        Element(
            type=ElementType.HEADING,
            text="Giriş ve Kapsam",
            page_start=1,
            page_end=1,
            heading_path=[],
        ),
        Element(
            type=ElementType.PARAGRAPH,
            text="Bu doküman müşteri haklarını ve teslimat prosedürlerini detaylandırır.",
            page_start=1,
            page_end=1,
            heading_path=["Giriş ve Kapsam"],
        ),
        Element(
            type=ElementType.HEADING,
            text="Garanti ve Değişim Koşulları",
            page_start=1,
            page_end=1,
            heading_path=[],
        ),
        Element(
            type=ElementType.PARAGRAPH,
            text="Elektronik ürünler 2 yıl garanti kapsamındadır. Kurulum yetkili servisçe yapılmalıdır.",
            page_start=1,
            page_end=2,
            heading_path=["Garanti ve Değişim Koşulları"],
        ),
        Element(
            type=ElementType.TABLE,
            text=(
                "| Kategori | Süre |\n"
                "|---|---|\n"
                "| Telefon | 2 Yıl |\n"
                "| Bilgisayar | 3 Yıl |\n"
                "| Aksesuar | 1 Yıl |"
            ),
            page_start=2,
            page_end=2,
            heading_path=["Garanti ve Değişim Koşulları"],
        ),
        Element(
            type=ElementType.HEADING,
            text="İstisnai Durumlar",
            page_start=2,
            page_end=2,
            heading_path=[],
        ),
        Element(
            type=ElementType.LIST,
            text=(
                "- Kullanıcı hatasından kaynaklanan kırılmalar.\n"
                "- Sıvı teması sonucu oluşan arızalar.\n"
                "- Yetkisiz müdahale tespit edilen cihazlar."
            ),
            page_start=3,
            page_end=3,
            heading_path=["İstisnai Durumlar"],
        ),
    ]
    return ParsedDocument(
        source_file="contract_test_doc.pdf",
        elements=elements,
        quality=QualityReport(page_count=3, status="ok"),
        parser_name="synthetic_parser",
        parser_version="1.0",
    )


def test_factory_creation():
    tokenizer = WhitespaceTokenizer()
    config = ChunkingConfig()

    fixed = get_chunker("fixed", tokenizer, config)
    assert fixed.name == ChunkStrategy.FIXED

    recursive = get_chunker(ChunkStrategy.RECURSIVE, tokenizer, config)
    assert recursive.name == ChunkStrategy.RECURSIVE

    structure = get_chunker("structure", tokenizer, config)
    assert structure.name == ChunkStrategy.STRUCTURE

    with pytest.raises(ValueError, match="Unknown chunking strategy 'invalid'"):
        get_chunker("invalid", tokenizer, config)


# ==============================================================================
# PARAMETRIC CONTRACT TESTS (3 Chunker x 8 Test)
# ==============================================================================


@pytest.mark.parametrize(
    "strategy", [ChunkStrategy.FIXED, ChunkStrategy.RECURSIVE, ChunkStrategy.STRUCTURE]
)
def test_contract_1_no_empty_chunks(strategy, rich_synthetic_document):
    """1. Kural: Hiçbir chunk boş metin içeremez (text.strip() != '')."""
    tokenizer = WhitespaceTokenizer()
    config = ChunkingConfig(max_tokens=40, overlap_tokens=10, min_tokens=10)
    chunker = get_chunker(strategy, tokenizer, config)

    chunks = chunker.chunk(rich_synthetic_document)
    assert len(chunks) > 0
    for c in chunks:
        assert c.text.strip() != "", f"{strategy} ürettiği chunk boş metin içeriyor!"


@pytest.mark.parametrize(
    "strategy", [ChunkStrategy.FIXED, ChunkStrategy.RECURSIVE, ChunkStrategy.STRUCTURE]
)
def test_contract_2_max_tokens_budget(strategy, rich_synthetic_document):
    """2. Kural: Chunk'lar max_tokens sınırını aşamaz."""
    tokenizer = WhitespaceTokenizer()
    max_tokens = 40
    config = ChunkingConfig(max_tokens=max_tokens, overlap_tokens=10, min_tokens=10)
    chunker = get_chunker(strategy, tokenizer, config)

    chunks = chunker.chunk(rich_synthetic_document)
    for c in chunks:
        tokens = tokenizer.count(c.text)
        assert (
            tokens <= max_tokens
        ), f"{strategy} limit aşıldı: {tokens} > {max_tokens} in '{c.text}'"


@pytest.mark.parametrize(
    "strategy", [ChunkStrategy.FIXED, ChunkStrategy.RECURSIVE, ChunkStrategy.STRUCTURE]
)
def test_contract_3_coverage(strategy, rich_synthetic_document):
    """3. Kural: Dokümandaki kelimeler chunk'lar tarafından eksiksiz kapsanmalıdır."""
    tokenizer = WhitespaceTokenizer()
    config = ChunkingConfig(max_tokens=30, overlap_tokens=5, min_tokens=5)
    chunker = get_chunker(strategy, tokenizer, config)

    chunks = chunker.chunk(rich_synthetic_document)

    # Dokümandaki önemli ayırt edici anahtar kelimeler chunk'larda mutlaka bulunmalı
    key_terms = [
        "haklarını",
        "prosedürlerini",
        "Elektronik",
        "Telefon",
        "Bilgisayar",
        "Aksesuar",
        "Kullanıcı",
        "teması",
        "müdahale",
    ]

    combined_text = "\n".join(c.text for c in chunks)
    for term in key_terms:
        assert term in combined_text, f"{strategy} kapsamasında '{term}' eksik!"


@pytest.mark.parametrize(
    "strategy", [ChunkStrategy.FIXED, ChunkStrategy.RECURSIVE, ChunkStrategy.STRUCTURE]
)
def test_contract_4_chunk_index_and_char_progression(strategy, rich_synthetic_document):
    """4. Kural: chunk_index 0'dan ardışık gitmeli, char_start zamanla azalmamalıdır."""
    tokenizer = WhitespaceTokenizer()
    config = ChunkingConfig(max_tokens=40, overlap_tokens=10, min_tokens=10)
    chunker = get_chunker(strategy, tokenizer, config)

    chunks = chunker.chunk(rich_synthetic_document)
    for idx, c in enumerate(chunks):
        assert c.chunk_index == idx
        if idx > 0:
            assert c.char_start >= chunks[idx - 1].char_start


@pytest.mark.parametrize(
    "strategy", [ChunkStrategy.FIXED, ChunkStrategy.RECURSIVE, ChunkStrategy.STRUCTURE]
)
def test_contract_5_page_ranges_valid(strategy, rich_synthetic_document):
    """5. Kural: page_start >= 1, page_end >= page_start ve doküman sınırları içinde olmalı."""
    tokenizer = WhitespaceTokenizer()
    config = ChunkingConfig(max_tokens=40, overlap_tokens=10, min_tokens=10)
    chunker = get_chunker(strategy, tokenizer, config)

    chunks = chunker.chunk(rich_synthetic_document)
    for c in chunks:
        assert c.page_start >= 1
        assert c.page_end >= c.page_start
        assert c.page_end <= rich_synthetic_document.quality.page_count


@pytest.mark.parametrize(
    "strategy", [ChunkStrategy.FIXED, ChunkStrategy.RECURSIVE, ChunkStrategy.STRUCTURE]
)
def test_contract_6_determinism(strategy, rich_synthetic_document):
    """6. Kural: Aynı doküman ve config ile iki kez çalıştırıldığında aynı id ve metinleri üretmeli."""
    tokenizer = WhitespaceTokenizer()
    config1 = ChunkingConfig(max_tokens=35, overlap_tokens=10, min_tokens=10)
    config2 = ChunkingConfig(max_tokens=50, overlap_tokens=10, min_tokens=10)

    chunker_a = get_chunker(strategy, tokenizer, config1)
    chunker_b = get_chunker(strategy, tokenizer, config1)

    chunks_a = chunker_a.chunk(rich_synthetic_document)
    chunks_b = chunker_b.chunk(rich_synthetic_document)

    assert [c.id for c in chunks_a] == [c.id for c in chunks_b]
    assert [c.text for c in chunks_a] == [c.text for c in chunks_b]

    # Config değişince ID'ler değişmeli
    chunker_diff = get_chunker(strategy, tokenizer, config2)
    chunks_diff = chunker_diff.chunk(rich_synthetic_document)
    assert chunks_a[0].id != chunks_diff[0].id


@pytest.mark.parametrize(
    "strategy", [ChunkStrategy.FIXED, ChunkStrategy.RECURSIVE, ChunkStrategy.STRUCTURE]
)
def test_contract_7_unique_ids_within_document(strategy, rich_synthetic_document):
    """7. Kural: Doküman içindeki tüm chunk ID'leri benzersiz (unique) olmalıdır."""
    tokenizer = WhitespaceTokenizer()
    config = ChunkingConfig(max_tokens=30, overlap_tokens=5, min_tokens=5)
    chunker = get_chunker(strategy, tokenizer, config)

    chunks = chunker.chunk(rich_synthetic_document)
    ids = [c.id for c in chunks]
    assert len(ids) == len(set(ids)), f"{strategy} duplicate chunk id üretti!"


@pytest.mark.parametrize(
    "strategy", [ChunkStrategy.FIXED, ChunkStrategy.RECURSIVE, ChunkStrategy.STRUCTURE]
)
def test_contract_8_empty_document_safe(strategy):
    """8. Kural: Boş doküman verildiğinde hata vermeden boş liste dönmelidir."""
    tokenizer = WhitespaceTokenizer()
    config = ChunkingConfig()
    chunker = get_chunker(strategy, tokenizer, config)

    empty_doc = ParsedDocument(
        source_file="empty.pdf",
        elements=[],
        quality=QualityReport(page_count=0, status="ok"),
        parser_name="mock",
        parser_version="1.0",
    )
    chunks = chunker.chunk(empty_doc)
    assert chunks == []
