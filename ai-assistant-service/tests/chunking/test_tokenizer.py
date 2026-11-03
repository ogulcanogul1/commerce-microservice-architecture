import pytest
from app.rag.chunking.tokenizer import (
    Tokenizer,
    WhitespaceTokenizer,
    TiktokenTokenizer,
)


def test_tokenizer_protocol_conformance():
    """Verify that both tokenizers conform to the Tokenizer Protocol at runtime."""
    ws = WhitespaceTokenizer()
    tt = TiktokenTokenizer()

    assert isinstance(ws, Tokenizer)
    assert isinstance(tt, Tokenizer)


def test_whitespace_tokenizer_empty_and_whitespace():
    ws = WhitespaceTokenizer()
    assert ws.count("") == 0
    assert ws.token_spans("") == []
    assert ws.count("   \n\t  ") == 0
    assert ws.token_spans("   \n\t  ") == []


def test_whitespace_tokenizer_normal_text():
    ws = WhitespaceTokenizer()
    text = "Hızlı kahverengi   tilki çitin\nüzerinden atlar."
    assert ws.count(text) == 6

    spans = ws.token_spans(text)
    assert len(spans) == 6

    words = [text[start:end] for start, end in spans]
    assert words == ["Hızlı", "kahverengi", "tilki", "çitin", "üzerinden", "atlar."]


def test_tiktoken_tokenizer_empty():
    tt = TiktokenTokenizer()
    assert tt.count("") == 0
    assert tt.token_spans("") == []


def test_tiktoken_tokenizer_turkish_utf8_alignment():
    """Verify that tiktoken spans cover the entire text seamlessly without breaking multi-byte characters."""
    tt = TiktokenTokenizer()
    text = "Çağrı merkezi ve şikâyet yönetimi: İade, değişim & garanti."

    count = tt.count(text)
    assert count > 0

    spans = tt.token_spans(text)
    assert len(spans) == count

    # In tiktoken, tokens partition the entire byte/char stream seamlessly
    assert spans[0][0] == 0
    assert spans[-1][1] == len(text)

    # Contiguity check: each span starts where the previous one ended
    for i in range(len(spans) - 1):
        assert spans[i][1] == spans[i + 1][0], f"Gap or overlap at index {i}: {spans[i]} vs {spans[i+1]}"

    # Slice reconstruction must exactly match the original string
    reconstructed = "".join(text[start:end] for start, end in spans)
    assert reconstructed == text

    # Ensure no sliced fragment has unicode replacement characters or decode errors
    for start, end in spans:
        fragment = text[start:end]
        assert "\ufffd" not in fragment


def test_tiktoken_tokenizer_special_characters_and_emojis():
    tt = TiktokenTokenizer()
    text = "Ücret: 1.250,50 TL ✨ (KDV %20 dahil) [Ref: #9876]"

    spans = tt.token_spans(text)
    reconstructed = "".join(text[start:end] for start, end in spans)
    assert reconstructed == text
