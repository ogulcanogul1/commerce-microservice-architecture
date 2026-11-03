import pytest
from app.rag.chunking.flatten import Span, FlatDocument, flatten
from app.rag.ingestion.models import Element, ElementType, ParsedDocument, QualityReport


@pytest.fixture
def sample_parsed_document() -> ParsedDocument:
    elements = [
        Element(
            type=ElementType.HEADING,
            text="Bölüm 1: Giriş ve Kapsam",
            page_start=1,
            page_end=1,
            heading_path=[],
        ),
        Element(
            type=ElementType.PARAGRAPH,
            text="Bu doküman e-ticaret platformumuzun iade ve değişim süreçlerini açıklar.",
            page_start=1,
            page_end=1,
            heading_path=["Bölüm 1: Giriş ve Kapsam"],
        ),
        Element(
            type=ElementType.TABLE,
            text="| Ürün Grubu | İade Süresi |\n|---|---|\n| Elektronik | 14 Gün |",
            page_start=1,
            page_end=2,
            heading_path=["Bölüm 1: Giriş ve Kapsam"],
        ),
    ]
    return ParsedDocument(
        source_file="test_policy.pdf",
        elements=elements,
        quality=QualityReport(page_count=2, status="ok"),
        parser_name="mock_parser",
        parser_version="1.0",
    )


def test_flatten_empty_document():
    doc = ParsedDocument(
        source_file="empty.pdf",
        elements=[],
        quality=QualityReport(page_count=0, status="ok"),
        parser_name="mock_parser",
        parser_version="1.0",
    )
    flat = flatten(doc)
    assert flat.text == ""
    assert flat.spans == []
    assert flat.source_file == "empty.pdf"
    assert flat.spans_in(0, 10) == []
    assert flat.metadata_for(0, 10) == (1, 1, [], [])


def test_flatten_spans_coverage_and_continuity(sample_parsed_document):
    flat = flatten(sample_parsed_document)

    assert len(flat.spans) == 3
    assert flat.source_file == "test_policy.pdf"

    # Her span'in dilimi orijinal element metniyle birebir aynı olmalı
    for span, element in zip(flat.spans, sample_parsed_document.elements):
        slice_text = flat.text[span.char_start : span.char_end]
        assert slice_text == element.text
        assert span.element_type == element.type
        assert span.page_start == element.page_start
        assert span.page_end == element.page_end

    # Elementler arasında '\n\n' ayırıcı bulunmalı
    sep = "\n\n"
    s0, s1, s2 = flat.spans
    assert flat.text[s0.char_end : s1.char_start] == sep
    assert flat.text[s1.char_end : s2.char_start] == sep


def test_metadata_for_single_span_inside_paragraph(sample_parsed_document):
    flat = flatten(sample_parsed_document)
    p_span = flat.spans[1]

    # Paragrafın tam ortasından bir dilim aldığımızda
    start = p_span.char_start + 5
    end = p_span.char_end - 5
    page_start, page_end, heading_path, element_types = flat.metadata_for(start, end)

    assert page_start == 1
    assert page_end == 1
    assert heading_path == ["Bölüm 1: Giriş ve Kapsam"]
    assert element_types == [ElementType.PARAGRAPH]


def test_metadata_for_span_across_paragraph_and_table(sample_parsed_document):
    flat = flatten(sample_parsed_document)
    p_span = flat.spans[1]
    t_span = flat.spans[2]

    # Paragrafın sonundan başlayıp tablonun içine uzanan dilim
    start = p_span.char_end - 10
    end = t_span.char_start + 20
    page_start, page_end, heading_path, element_types = flat.metadata_for(start, end)

    assert page_start == 1
    assert page_end == 2  # Tablo sayfa 2'ye taşıyor
    assert heading_path == ["Bölüm 1: Giriş ve Kapsam"]
    assert element_types == [ElementType.PARAGRAPH, ElementType.TABLE]


def test_metadata_for_heading_element_includes_own_text(sample_parsed_document):
    flat = flatten(sample_parsed_document)
    h_span = flat.spans[0]

    # Başlığın kendisini kapsayan bir dilim
    start = h_span.char_start
    end = h_span.char_end
    _, _, heading_path, element_types = flat.metadata_for(start, end)

    # Ingestion kuralı: HEADING'in heading_path'i boş olsa bile, chunker için başlık metni yola eklenir
    assert heading_path == ["Bölüm 1: Giriş ve Kapsam"]
    assert element_types == [ElementType.HEADING]


def test_metadata_for_whitespace_gap_fallback(sample_parsed_document):
    flat = flatten(sample_parsed_document)
    s0, s1 = flat.spans[0], flat.spans[1]

    # Tam s0 ile s1 arasındaki '\n\n' boşluğuna denk gelen bir aralık
    start = s0.char_end
    end = s1.char_start
    page_start, page_end, heading_path, element_types = flat.metadata_for(start, end)

    # Fallback olarak önceki span'in bilgilerini taşımalı
    assert page_start == 1
    assert page_end == 1
    assert element_types == [ElementType.HEADING]
