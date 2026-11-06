from app.rag.chunking.models import Chunk, ChunkStrategy
from app.rag.generation.citations import (
    cited_numbers,
    extract_citation_numbers,
    is_abstain,
    split_sentences,
    validate_answer,
)
from app.rag.generation.models import ContextBlock


def _make_block(number: int, text: str, header: str | None = None) -> ContextBlock:
    chunk = Chunk(
        id=f"c{number}",
        text=text,
        source_file="iade.pdf",
        chunk_index=0,
        page_start=1,
        page_end=1,
        char_start=0,
        char_end=len(text),
        token_count=10,
        strategy=ChunkStrategy.STRUCTURE,
    )
    hdr = header or f"[{number}] (iade.pdf, s. 1)"
    return ContextBlock(number=number, chunk=chunk, header=hdr, token_count=15)


def test_validate_answer_good_answer() -> None:
    # Kaynak 1 metninde 14 sayısı yer alıyor
    block1 = _make_block(1, "Teslimden itibaren 14 gün içinde cayma hakkı kullanılabilir. Hijyen bandı açılmış ürünler iade edilemez.")
    blocks = [block1]

    good_answer = (
        "Teslimden itibaren 14 gün içinde iade hakkınız var [1]. "
        "Hijyen bandı açılmış kozmetikte iade yapılamaz [1]."
    )
    issues = validate_answer(good_answer, blocks)
    assert issues == []


def test_validate_answer_bad_answer_with_three_specific_issues() -> None:
    # 2 kaynak tanımlı; kaynak 1'de 14 var, 30 yok.
    block1 = _make_block(1, "İade süresi 14 gündür.")
    block2 = _make_block(2, "Kargo gönderimi anlaşmalı kargo ile yapılır.")
    blocks = [block1, block2]

    bad_answer = (
        "30 gün içinde iade edebilirsiniz [1]. "
        "Para iadesi 10 iş günü sürer [3]. "
        "Kargo ücretsizdir."
    )
    issues = validate_answer(bad_answer, blocks)

    assert len(issues) == 3
    issue_types = [i.type for i in issues]

    # 1. Sayı kaynakta yok (30)
    assert "number_not_in_source" in issue_types
    num_issue = next(i for i in issues if i.type == "number_not_in_source")
    assert num_issue.detail == "30"

    # 2. Geçersiz kaynak numarası ([3] çünkü sadece 2 blok var)
    assert "invalid_citation" in issue_types
    inv_issue = next(i for i in issues if i.type == "invalid_citation")
    assert inv_issue.detail == "[3]"

    # 3. Atıfsız cümle ("Kargo ücretsizdir.")
    assert "uncited_sentence" in issue_types
    uncited_issue = next(i for i in issues if i.type == "uncited_sentence")
    assert "Kargo ücretsizdir." in uncited_issue.sentence


def test_citation_after_dot_binding() -> None:
    # Noktadan sonra gelen [1] önceki cümleye bağlanmalı ve geçerli olmalı
    blocks = [_make_block(1, "İade süresi 14 gündür.")]
    answer = "İade süresi 14 gündür. [1]"

    sentences = split_sentences(answer)
    assert len(sentences) == 1
    assert sentences[0] == "İade süresi 14 gündür. [1]"

    issues = validate_answer(answer, blocks)
    assert issues == []


def test_number_formatting_with_thousand_separator() -> None:
    # Kaynakta 1.000 TL var
    block_with_num = _make_block(1, "Sipariş tutarı 1.000 TL üzerinde ise kargo bedavadır.")
    answer = "Toplam 1.000 TL [1]."

    # Kaynakta varken sorun yok
    assert validate_answer(answer, [block_with_num]) == []

    # Kaynakta 1.000 yokken sorun var
    block_without_num = _make_block(1, "Kargo ücretlidir.")
    issues = validate_answer(answer, [block_without_num])
    assert any(i.type == "number_not_in_source" for i in issues)


def test_date_format_not_split() -> None:
    text = "Sözleşme 14.05.2026 tarihinden sonra [1] geçerlidir."
    sentences = split_sentences(text)
    assert len(sentences) == 1
    assert "14.05.2026" in sentences[0]


def test_abbreviation_not_split() -> None:
    text = "Kozmetik vb. ürünlerde [1] iade yapılamaz."
    sentences = split_sentences(text)
    assert len(sentences) == 1
    assert "vb." in sentences[0]


def test_is_abstain_cases() -> None:
    assert is_abstain("BULUNAMADI") is True
    assert is_abstain("bulunamadı.") is True
    assert is_abstain("Kaynaklarda BULUNAMADI") is True
    assert is_abstain("Bu konuda bilgi bulunamadı maalesef.") is True
    assert is_abstain("Teslimden itibaren 14 gün içinde iade edebilirsiniz [1].") is False
    assert is_abstain("") is False


def test_empty_answer_validation() -> None:
    blocks = [_make_block(1, "Metin")]
    issues_empty = validate_answer("", blocks)
    assert len(issues_empty) == 1
    assert issues_empty[0].type == "empty_answer"

    issues_whitespace = validate_answer("   ", blocks)
    assert len(issues_whitespace) == 1
    assert issues_whitespace[0].type == "empty_answer"


def test_extract_and_cited_numbers() -> None:
    sentence = "Bu konuda bilgi [1][2] ve ayrıca [1] nolu maddede [4] belirtilmiştir."
    nums = extract_citation_numbers(sentence)
    assert nums == [1, 2, 4]

    full_answer = "İlk cümle [2]. İkinci cümle [1][2]. Üçüncü cümle [3]."
    all_cited = cited_numbers(full_answer)
    assert all_cited == [2, 1, 3]


def test_is_abstain_ignores_words_merely_starting_with_marker() -> None:
    assert not is_abstain("Adres bulunamadığında kargo şubeye döner [1].")
    assert is_abstain("Bulunamadı.")


def test_split_sentences_keeps_list_numbers_attached() -> None:
    assert split_sentences("1. İade 14 gündür [1].\n2. Kargo ücretsizdir [1].") == [
        "1. İade 14 gündür [1].",
        "2. Kargo ücretsizdir [1].",
    ]


def test_split_sentences_does_not_split_on_bkz() -> None:
    assert len(split_sentences("Kargo ücretsiz değildir (bkz. s. 3) [1].")) == 1


def test_numbered_list_answer_passes_validation() -> None:
    blocks = [_make_block(1, "İade süresi 14 gündür. Kargo ücretsizdir.")]
    assert validate_answer("1. İade 14 gündür [1].\n2. Kargo ücretsizdir [1].", blocks) == []
