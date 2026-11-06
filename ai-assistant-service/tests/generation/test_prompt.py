from app.rag.chunking.models import Chunk, ChunkStrategy
from app.rag.generation.models import ContextBlock, ValidationIssue
from app.rag.generation.prompt import (
    ABSTAIN_MARKER,
    SYSTEM_PROMPT,
    build_messages,
    build_retry_messages,
)


def _make_block(number: int, header: str, text: str) -> ContextBlock:
    chunk = Chunk(
        id=f"c{number}",
        text=text,
        source_file="test.pdf",
        chunk_index=0,
        page_start=1,
        page_end=1,
        char_start=0,
        char_end=len(text),
        token_count=10,
        strategy=ChunkStrategy.STRUCTURE,
    )
    return ContextBlock(number=number, chunk=chunk, header=header, token_count=15)


def test_system_prompt_contains_critical_grounding_rules() -> None:
    assert ABSTAIN_MARKER in SYSTEM_PROMPT
    assert "BULUNAMADI" in SYSTEM_PROMPT
    assert "[1]" in SYSTEM_PROMPT
    assert "<kaynaklar>" in SYSTEM_PROMPT
    assert "müşteri destek asistanısın" in SYSTEM_PROMPT


def test_build_messages_structure_and_ordering() -> None:
    blocks = [
        _make_block(1, "[1] (sozlesme.pdf, s. 1)", "İade süresi 14 gündür."),
        _make_block(2, "[2] (kargo.pdf, s. 2)", "Kargo ücretsizdir."),
    ]
    question = "İade süresi kaç gün?"

    messages = build_messages(question, blocks)

    assert len(messages) == 2
    assert messages[0].role == "system"
    assert SYSTEM_PROMPT == messages[0].content

    assert messages[1].role == "user"
    user_content = messages[1].content
    assert "<kaynaklar>" in user_content
    assert "</kaynaklar>" in user_content
    assert "[1] (sozlesme.pdf, s. 1)" in user_content
    assert "İade süresi 14 gündür." in user_content
    assert "[2] (kargo.pdf, s. 2)" in user_content
    assert "Kargo ücretsizdir." in user_content

    # Kaynaklar sorudan önce gelmeli
    sources_pos = user_content.find("</kaynaklar>")
    question_pos = user_content.find(f"Soru: {question}")
    assert sources_pos < question_pos


def test_build_retry_messages_includes_history_and_issue_summaries() -> None:
    blocks = [
        _make_block(1, "[1] (doc1.pdf, s. 1)", "Metin 1"),
        _make_block(2, "[2] (doc2.pdf, s. 2)", "Metin 2"),
    ]
    question = "Deneme sorusu"
    previous_answer = "Yanlış cevap metni"

    # 7 farklı sorun üretelim
    issues = [
        ValidationIssue(type="uncited_sentence", sentence="Bu cümlede atıf yok."),
        ValidationIssue(type="invalid_citation", sentence="Hatalı kaynak.", detail="[4]"),
        ValidationIssue(type="number_not_in_source", sentence="30 gün sürer.", detail="30"),
        ValidationIssue(type="empty_answer", sentence=""),
        ValidationIssue(type="uncited_sentence", sentence="İkinci atıfsız cümle."),
        ValidationIssue(type="invalid_citation", sentence="Başka geçersiz.", detail="[5]"),
        ValidationIssue(type="number_not_in_source", sentence="100 TL tutar.", detail="100"),
    ]

    messages = build_retry_messages(question, blocks, previous_answer, issues)

    assert len(messages) == 4
    assert messages[0].role == "system"
    assert messages[1].role == "user"
    assert messages[2].role == "assistant"
    assert messages[2].content == previous_answer

    assert messages[3].role == "user"
    retry_text = messages[3].content

    # İlk 5 sorun açıkça madde olarak listelenmeli
    assert "Şu cümlede kaynak numarası belirtilmemiş: «Bu cümlede atıf yok.»" in retry_text
    assert "Geçersiz kaynak numarası [4] kullanılmış" in retry_text
    assert "«30» sayısı atıf yaptığın kaynakta geçmiyor" in retry_text
    assert "Yanıt boş bırakılmış" in retry_text
    assert "Şu cümlede kaynak numarası belirtilmemiş: «İkinci atıfsız cümle.»" in retry_text

    # Kalan 2 sorun özetlenmeli
    assert "...ve 2 sorun daha" in retry_text

    # Kural tekrarı içermeli
    assert "BULUNAMADI" in retry_text
