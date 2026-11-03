import pytest
from app.rag.chunking.base import Chunker
from app.rag.chunking.models import ChunkingConfig, ChunkStrategy
from app.rag.chunking.strategies.structure_aware import StructureAwareChunker
from app.rag.chunking.tokenizer import WhitespaceTokenizer
from app.rag.ingestion.models import Element, ElementType, ParsedDocument, QualityReport


def test_structure_aware_protocol_conformance():
    tokenizer = WhitespaceTokenizer()
    config = ChunkingConfig()
    chunker = StructureAwareChunker(tokenizer, config)
    assert isinstance(chunker, Chunker)
    assert chunker.name == ChunkStrategy.STRUCTURE


def test_two_sections_respect_section_boundaries():
    """Chunk'lar bölüm sınırlarını aşmamalı; her chunk ait olduğu başlık yolunu taşımalıdır."""
    tokenizer = WhitespaceTokenizer()
    elements = [
        Element(
            type=ElementType.HEADING,
            text="Bölüm 1",
            page_start=1,
            page_end=1,
            heading_path=[],
        ),
        Element(
            type=ElementType.PARAGRAPH,
            text="Bölüm 1 açıklaması ve detayları.",
            page_start=1,
            page_end=1,
            heading_path=["Bölüm 1"],
        ),
        Element(
            type=ElementType.HEADING,
            text="Bölüm 2",
            page_start=2,
            page_end=2,
            heading_path=[],
        ),
        Element(
            type=ElementType.PARAGRAPH,
            text="Bölüm 2 açıklaması ve farklı koşulları.",
            page_start=2,
            page_end=2,
            heading_path=["Bölüm 2"],
        ),
    ]
    doc = ParsedDocument(
        source_file="sections.pdf",
        elements=elements,
        quality=QualityReport(page_count=2, status="ok"),
        parser_name="mock",
        parser_version="1.0",
    )

    config = ChunkingConfig(max_tokens=50, min_tokens=10)
    chunker = StructureAwareChunker(tokenizer, config)
    chunks = chunker.chunk(doc)

    assert len(chunks) == 2
    assert chunks[0].heading_path == ["Bölüm 1"]
    assert "Bölüm 1 açıklaması" in chunks[0].text
    assert chunks[0].page_start == 1

    assert chunks[1].heading_path == ["Bölüm 2"]
    assert "Bölüm 2 açıklaması" in chunks[1].text
    assert chunks[1].page_start == 2


def test_large_table_splits_and_preserves_header():
    """Bütçeyi aşan tablo bölündüğünde her parçanın başında başlık ve ayırıcı yer almalıdır."""
    tokenizer = WhitespaceTokenizer()
    # 5 satırlı tablo
    table_text = (
        "| Ürün | Garanti |\n"
        "|---|---|\n"
        "| Telefon | 2 Yıl |\n"
        "| Tablet | 2 Yıl |\n"
        "| Bilgisayar | 3 Yıl |\n"
        "| Televizyon | 2 Yıl |"
    )

    elements = [
        Element(
            type=ElementType.TABLE,
            text=table_text,
            page_start=1,
            page_end=1,
            heading_path=["Garanti Tablosu"],
        )
    ]
    doc = ParsedDocument(
        source_file="table.pdf",
        elements=elements,
        quality=QualityReport(page_count=1, status="ok"),
        parser_name="mock",
        parser_version="1.0",
    )

    # Düşük bütçe: her chunk sadece 1-2 veri satırı alabilsin
    # max_tokens=15, overlap_tokens=2, min_tokens=5
    config = ChunkingConfig(max_tokens=15, overlap_tokens=2, min_tokens=5)
    chunker = StructureAwareChunker(tokenizer, config)
    chunks = chunker.chunk(doc)

    assert len(chunks) >= 2

    # Her parçanın başında başlık ve ayırıcı olmalı
    header_prefix = "| Ürün | Garanti |\n|---|---|"
    for c in chunks:
        assert c.text.startswith(header_prefix)
        assert c.token_count <= 15

    # Tüm ürünlerin en az bir parçada yer aldığı doğrulanmalı
    combined_text = "\n".join(c.text for c in chunks)
    for prod in ["Telefon", "Tablet", "Bilgisayar", "Televizyon"]:
        assert prod in combined_text


def test_exceeding_paragraph_splits_within_section():
    """Bütçeyi aşan tek bir paragraf alt parçalara ayrılmalı ve aynı heading_path'i korumalıdır."""
    tokenizer = WhitespaceTokenizer()
    long_text = " ".join([f"cumle_kelimesi_{i}." for i in range(25)])

    elements = [
        Element(
            type=ElementType.HEADING,
            text="Uzun Paragraf Başlığı",
            page_start=1,
            page_end=1,
        ),
        Element(
            type=ElementType.PARAGRAPH,
            text=long_text,
            page_start=1,
            page_end=1,
            heading_path=["Uzun Paragraf Başlığı"],
        ),
    ]
    doc = ParsedDocument(
        source_file="long_p.pdf",
        elements=elements,
        quality=QualityReport(page_count=1, status="ok"),
        parser_name="mock",
        parser_version="1.0",
    )

    config = ChunkingConfig(max_tokens=15, overlap_tokens=2, min_tokens=5)
    chunker = StructureAwareChunker(tokenizer, config)
    chunks = chunker.chunk(doc)

    assert len(chunks) >= 2
    for c in chunks:
        assert c.heading_path == ["Uzun Paragraf Başlığı"]
        assert c.token_count <= 15


def test_small_sibling_sections_merge():
    """Aynı üst başlığa sahip min_tokens altındaki kardeş bölümler birleşmelidir."""
    tokenizer = WhitespaceTokenizer()
    elements = [
        # 1. Kardeş bölüm: "Elektronik > Telefon" (Küçük metin: 3 kelime)
        Element(
            type=ElementType.HEADING,
            text="Telefon",
            page_start=1,
            page_end=1,
            heading_path=["Elektronik"],
        ),
        Element(
            type=ElementType.PARAGRAPH,
            text="Telefon iade şartı.",
            page_start=1,
            page_end=1,
            heading_path=["Elektronik", "Telefon"],
        ),
        # 2. Kardeş bölüm: "Elektronik > Tablet" (Küçük metin: 3 kelime)
        Element(
            type=ElementType.HEADING,
            text="Tablet",
            page_start=1,
            page_end=1,
            heading_path=["Elektronik"],
        ),
        Element(
            type=ElementType.PARAGRAPH,
            text="Tablet iade şartı.",
            page_start=1,
            page_end=1,
            heading_path=["Elektronik", "Tablet"],
        ),
    ]
    doc = ParsedDocument(
        source_file="siblings.pdf",
        elements=elements,
        quality=QualityReport(page_count=1, status="ok"),
        parser_name="mock",
        parser_version="1.0",
    )

    # min_tokens=10 -> Her iki bölüm de 10 token'ın altında ve toplamları 15 token'ı aşmıyor
    config = ChunkingConfig(max_tokens=30, overlap_tokens=5, min_tokens=10)
    chunker = StructureAwareChunker(tokenizer, config)
    chunks = chunker.chunk(doc)

    # İki kardeş bölüm tek bir ortak üst başlık ("Elektronik") altında birleşmeli
    assert len(chunks) == 1
    assert chunks[0].heading_path == ["Elektronik"]
    assert "Telefon iade şartı." in chunks[0].text
    assert "Tablet iade şartı." in chunks[0].text


def test_breadcrumb_disabled():
    """include_breadcrumb=False olduğunda context_prefix boş olmalı ve embedding_text == text olmalıdır."""
    tokenizer = WhitespaceTokenizer()
    elements = [
        Element(
            type=ElementType.HEADING,
            text="Başlık",
            page_start=1,
            page_end=1,
        ),
        Element(
            type=ElementType.PARAGRAPH,
            text="İçerik yazısı.",
            page_start=1,
            page_end=1,
            heading_path=["Başlık"],
        ),
    ]
    doc = ParsedDocument(
        source_file="breadcrumb.pdf",
        elements=elements,
        quality=QualityReport(page_count=1, status="ok"),
        parser_name="mock",
        parser_version="1.0",
    )

    config = ChunkingConfig(include_breadcrumb=False)
    chunker = StructureAwareChunker(tokenizer, config)
    chunks = chunker.chunk(doc)

    assert len(chunks) == 1
    assert chunks[0].context_prefix == ""
    assert chunks[0].embedding_text == chunks[0].text


def test_isolate_tables_enabled():
    """isolate_tables=True olduğunda tablo önceki paragrafla aynı chunk'a konmaz."""
    tokenizer = WhitespaceTokenizer()
    elements = [
        Element(
            type=ElementType.PARAGRAPH,
            text="Aşağıdaki tablo garanti sürelerini listeler.",
            page_start=1,
            page_end=1,
        ),
        Element(
            type=ElementType.TABLE,
            text="| Cihaz | Yıl |\n|---|---|\n| TV | 2 |",
            page_start=1,
            page_end=1,
        ),
    ]
    doc = ParsedDocument(
        source_file="isolate.pdf",
        elements=elements,
        quality=QualityReport(page_count=1, status="ok"),
        parser_name="mock",
        parser_version="1.0",
    )

    # Bütçe 100 olmasına rağmen isolate_tables=True olduğu için ayrı chunk olmalı
    config = ChunkingConfig(max_tokens=100, isolate_tables=True)
    chunker = StructureAwareChunker(tokenizer, config)
    chunks = chunker.chunk(doc)

    assert len(chunks) == 2
    assert chunks[0].text == "Aşağıdaki tablo garanti sürelerini listeler."
    assert "| Cihaz | Yıl |" in chunks[1].text
