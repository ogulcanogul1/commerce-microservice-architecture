import pytest
from app.rag.chunking.base import Chunker
from app.rag.chunking.models import ChunkingConfig, ChunkStrategy
from app.rag.chunking.strategies.recursive import RecursiveChunker
from app.rag.chunking.tokenizer import WhitespaceTokenizer
from app.rag.ingestion.models import Element, ElementType, ParsedDocument, QualityReport


def test_recursive_chunker_protocol_conformance():
    tokenizer = WhitespaceTokenizer()
    config = ChunkingConfig()
    chunker = RecursiveChunker(tokenizer, config)
    assert isinstance(chunker, Chunker)
    assert chunker.name == ChunkStrategy.RECURSIVE


def test_recursive_empty_document():
    tokenizer = WhitespaceTokenizer()
    config = ChunkingConfig()
    chunker = RecursiveChunker(tokenizer, config)

    doc = ParsedDocument(
        source_file="empty.pdf",
        elements=[],
        quality=QualityReport(page_count=0, status="ok"),
        parser_name="mock",
        parser_version="1.0",
    )
    chunks = chunker.chunk(doc)
    assert chunks == []


def test_recursive_splits_on_paragraph_boundaries():
    """İki uzun paragraf arasında '\\n\\n' varken chunk sınırı paragraf ayırıcısına oturmalıdır."""
    tokenizer = WhitespaceTokenizer()
    # 25 kelimelik iki paragraf = 50 kelime
    # max_tokens=30, overlap=5, min_tokens=10
    p1 = " ".join([f"p1_w{i}" for i in range(25)])
    p2 = " ".join([f"p2_w{i}" for i in range(25)])
    text = f"{p1}\n\n{p2}"

    doc = ParsedDocument(
        source_file="doc_para.pdf",
        elements=[
            Element(
                type=ElementType.PARAGRAPH,
                text=text,
                page_start=1,
                page_end=1,
            )
        ],
        quality=QualityReport(page_count=1, status="ok"),
        parser_name="mock",
        parser_version="1.0",
    )

    config = ChunkingConfig(max_tokens=30, overlap_tokens=5, min_tokens=10)
    chunker = RecursiveChunker(tokenizer, config)

    chunks = chunker.chunk(doc)
    assert len(chunks) == 2

    # İlk chunk 1. paragraftan oluşmalı
    assert chunks[0].text.strip().startswith("p1_w0")
    assert chunks[0].text.strip().endswith("p1_w24")
    assert chunks[0].token_count == 25

    # İkinci chunk 2. paragrafı içermeli
    assert "p2_w0" in chunks[1].text
    assert chunks[1].text.strip().endswith("p2_w24")


def test_recursive_splits_long_paragraph_on_sentence_boundaries():
    """max_tokens'ı aşan tek bir paragraf, cümle sınırlarından bölünmelidir."""
    tokenizer = WhitespaceTokenizer()
    # 3 adet 15 kelimelik düzgün cümle = 45 kelime
    # Cümleler büyük harfle başlar ve noktayla biter.
    # max_tokens=35, overlap=10, min_tokens=10
    s1 = "Birinci cümlenin kelimeleri burada yer alıyor ve devam ediyor."  # 9 kelime
    s2 = "İkinci cümlenin detayları bu kısımda açıklanıyor ve bilgi veriyor."  # 9 kelime
    s3 = "Üçüncü cümlenin koşulları son olarak belirtiliyor ve tamamlanıyor."  # 9 kelime
    text = f"{s1} {s2} {s3}"

    doc = ParsedDocument(
        source_file="doc_sent.pdf",
        elements=[
            Element(
                type=ElementType.PARAGRAPH,
                text=text,
                page_start=1,
                page_end=1,
            )
        ],
        quality=QualityReport(page_count=1, status="ok"),
        parser_name="mock",
        parser_version="1.0",
    )

    config = ChunkingConfig(max_tokens=22, overlap_tokens=5, min_tokens=5)
    chunker = RecursiveChunker(tokenizer, config)

    chunks = chunker.chunk(doc)

    # Hiçbir chunk 22 token'ı aşmamalı
    for c in chunks:
        assert c.token_count <= 22

    # Chunklar cümleleri ortadan bölmemeli, tam cümle bitişlerinde ayrılmalı
    assert chunks[0].text.strip().endswith("ediyor.") or chunks[0].text.strip().endswith("veriyor.")


def test_recursive_splits_giant_text_without_separators():
    """Hiçbir noktalama veya satır sonu içermeyen devasa metin kelime/token düzeyinde bölünür."""
    tokenizer = WhitespaceTokenizer()
    words = [f"word{i}" for i in range(80)]
    text = " ".join(words)  # sadece boşluklar var

    doc = ParsedDocument(
        source_file="doc_words.pdf",
        elements=[
            Element(
                type=ElementType.PARAGRAPH,
                text=text,
                page_start=1,
                page_end=1,
            )
        ],
        quality=QualityReport(page_count=1, status="ok"),
        parser_name="mock",
        parser_version="1.0",
    )

    config = ChunkingConfig(max_tokens=30, overlap_tokens=5, min_tokens=10)
    chunker = RecursiveChunker(tokenizer, config)

    chunks = chunker.chunk(doc)
    assert len(chunks) >= 3

    for c in chunks:
        assert c.token_count <= 30

    # Kapsama tam olmalı
    all_chunk_words = set()
    for c in chunks:
        all_chunk_words.update(c.text.split())
    assert len(all_chunk_words) == 80


def test_recursive_merges_tiny_tail_chunk():
    """min_tokens'tan küçük son chunk öncekiyle sığıyorsa birleştirilmelidir."""
    tokenizer = WhitespaceTokenizer()
    # 20 kelimelik ilk kısım, 5 kelimelik ikinci kısım. max=30, min=10
    # 20 + 5 = 25 <= 30 -> tek chunkta birleşmeli
    text = " ".join([f"w{i}" for i in range(20)]) + "\n\n" + " ".join([f"tail{i}" for i in range(5)])

    doc = ParsedDocument(
        source_file="doc_tail.pdf",
        elements=[
            Element(
                type=ElementType.PARAGRAPH,
                text=text,
                page_start=1,
                page_end=1,
            )
        ],
        quality=QualityReport(page_count=1, status="ok"),
        parser_name="mock",
        parser_version="1.0",
    )

    config = ChunkingConfig(max_tokens=30, overlap_tokens=5, min_tokens=10)
    chunker = RecursiveChunker(tokenizer, config)

    chunks = chunker.chunk(doc)
    assert len(chunks) == 1
    assert "tail4" in chunks[0].text
