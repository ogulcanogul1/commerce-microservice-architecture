import re

# Korunacak Türkçe kısaltmalar (küçük harfle normalize karşılaştırılır)
ABBREVIATIONS: frozenset[str] = frozenset(
    {
        "dr",
        "prof",
        "doc",
        "doç",
        "uzm",
        "av",
        "ist",
        "ank",
        "izmir",
        "vb",
        "vs",
        "bkz",
        "sn",
        "no",
        "tel",
        "sk",
        "mah",
        "cad",
        "sok",
        "apt",
        "a.ş",
        "aş",
        "ltd",
        "şti",
        "sti",
        "örn",
        "orn",
        "yy",
        "sf",
        "mad",
        "tc",
        "t.c",
    }
)

# Cümle sonu noktalama işaretleri: nokta, ünlem, soru işareti, üç nokta
_PUNCT_RE = re.compile(r"([.!?…]+)")

# Noktalamadan sonra gelen boşluk ve büyük harf kontrolü (Türkçe büyük harfler dahil)
_NEXT_CHAR_RE = re.compile(r"^\s+([A-ZÇĞİÖŞÜ0-9\"'“(])")


def split_sentences(text: str) -> list[tuple[int, int]]:
    """Split text into sentence character spans [start, end) preserving full coverage.

    Features:
    - Turkish uppercase sensitivity (Ç, Ğ, İ, Ö, Ş, Ü).
    - Abbreviation protection (Dr., Prof., vb., sn., No., vb.).
    - Numbers, dates, and decimals protection (3.5, 14.02.2026, 4.1).
    - Seamless coverage: concatenating all sliced spans equals the original text.
    """
    if not text:
        return []

    spans: list[tuple[int, int]] = []
    text_len = len(text)
    sentence_start = 0

    for match in _PUNCT_RE.finditer(text):
        punct_end = match.end()
        punct_str = match.group(1)
        punct_start = match.start()

        # 1. Ondalık sayı, tarih veya madde numarası koruması: '3.5', '14.02.2026', '4.1'
        # Noktanın hemen öncesi ve sonrası rakam ise cümle sonu değildir
        if punct_str == "." and punct_start > 0 and punct_end < text_len:
            if text[punct_start - 1].isdigit() and text[punct_end].isdigit():
                continue

        # 2. Madde numarası koruması: '4.1 İade' (noktadan önce sayı dizisi varsa örn '1.' in '4.1 ')
        if punct_str == "." and punct_start > 0:
            if text[punct_start - 1].isdigit() and punct_end < text_len and text[punct_end] == " ":
                prev_space = text.rfind(" ", 0, punct_start)
                token_before = text[prev_space + 1 : punct_start]
                if "." in token_before and token_before.replace(".", "").isdigit():
                    continue

        # 3. Kısaltma koruması: 'Dr.', 'vb.', 'sn.', 'Ltd. Şti.'
        if "." in punct_str:
            word_match = re.search(r"([a-zA-ZçğıöşüÇĞİÖŞÜ.]+)\Z", text[:punct_start])
            if word_match:
                preceding_word = word_match.group(1).lower().rstrip(".")
                if preceding_word in ABBREVIATIONS:
                    continue

        # 4. Cümle sonundan sonra ne geliyor?
        rest = text[punct_end:]
        next_match = _NEXT_CHAR_RE.match(rest)

        # Eğer ardında boşluk + büyük harf/rakam varsa
        if next_match:
            space_len = next_match.start(1)
            sentence_end = punct_end + space_len
            spans.append((sentence_start, sentence_end))
            sentence_start = sentence_end
        elif punct_end == text_len:
            # Metnin en sonundaki noktalama
            spans.append((sentence_start, text_len))
            sentence_start = text_len

    # Kalan son parça varsa (örneğin son cümle noktasız bittiyse)
    if sentence_start < text_len:
        spans.append((sentence_start, text_len))

    return spans
