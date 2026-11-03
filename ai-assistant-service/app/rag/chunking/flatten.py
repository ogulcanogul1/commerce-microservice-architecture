import bisect
from dataclasses import dataclass
from app.rag.ingestion.models import Element, ElementType, ParsedDocument


@dataclass(frozen=True)
class Span:
    """Tek bir elementin (paragraf, başlık, tablo vb.) düz metin içindeki koordinat haritası.

    Fixed-Size veya Recursive chunker metni bölerken element kavramını bilmez, sadece karakter ofsetlerini bilir.
    Bu Span nesnesi sayesinde bir chunk'ın hangi elemente, hangi sayfaya ve hangi başlığa denk geldiğini anlarız.
    """
    char_start: int            # Elementin düz metindeki başlangıç karakter indeksi
    char_end: int              # Elementin düz metindeki bitiş karakter indeksi
    element_index: int         # Orijinal ParsedDocument.elements listesindeki sırası (0, 1, 2...)
    element_type: ElementType  # Elementin türü (HEADING, PARAGRAPH, TABLE, LIST)
    page_start: int            # Başladığı sayfa numarası (1-tabanlı)
    page_end: int              # Bittiği sayfa numarası (1-tabanlı)
    heading_path: list[str]    # Bu elementin ait olduğu başlık hiyerarşisi (örn: ['Bölüm 1', 'İadeler'])


@dataclass(frozen=True)
class FlatDocument:
    """ParsedDocument'ın tek bir düz metne ('\\n\\n' ile) dönüştürülmüş hali ve element koordinat indeksi."""
    text: str                  # Tüm elementlerin aralarında '\n\n' ile birleştirilmiş kesintisiz metni
    spans: list[Span]          # Sıralı element koordinat listesi (karakter aralıkları artan sırada)
    source_file: str           # Kaynak dosya adı veya yolu

    def spans_in(self, start: int, end: int) -> list[Span]:
        """Verilen [start, end) karakter aralığıyla kesişen tüm Span'leri hızlıca (İkili Arama ile) bulur.

        Kesişme Kuralı: Bir span [start, end) ile kesişir ancak ve ancak:
        span.char_start < end VE span.char_end > start ise.
        
        Neden bisect_right(span_ends, start)?
        span.char_end <= start olan tüm span'ler tamamen geride kalmıştır, onlara bakmaya gerek yoktur.
        İkili arama (binary search - O(log N)) ile ilk potansiyel span'e doğrudan zıplarız.
        """
        if start >= end or not self.spans:
            return []

        # Bitişi start'tan büyük olan İLK span'in indeksini ikili aramayla bul
        span_ends = [s.char_end for s in self.spans]
        idx = bisect.bisect_right(span_ends, start)

        overlapping: list[Span] = []
        for i in range(idx, len(self.spans)):
            span = self.spans[i]
            # Eğer span'in başlangıcı aradığımız bitişi (end) geçtiyse sonraki span'lere bakmaya gerek yok
            if span.char_start >= end:
                break
            # Gerçek kesişme kontrolü
            if span.char_end > start:
                overlapping.append(span)

        return overlapping

    def metadata_for(
        self, start: int, end: int
    ) -> tuple[int, int, list[str], list[ElementType]]:
        """Verilen [start, end) aralığı için (page_start, page_end, heading_path, element_types) üretir.

        Chunker bir metin dilimi oluşturduğunda bu metodu çağırır:
        1. page_start: Dilimin değdiği elementlerin en küçük sayfası (min).
        2. page_end: Dilimin değdiği elementlerin en büyük sayfası (max).
        3. heading_path: Chunk'ın başladığı yerdeki aktif başlık yolu.
           (Özel Durum: Eğer ilk elementin kendisi bir HEADING ise, başlık yoluna o başlığın metni de eklenir).
        4. element_types: Bu chunk'ın dokunduğu tüm element türleri (sırayla ve tekrarsız).
        """
        overlapping = self.spans_in(start, end)
        if not overlapping:
            # Sınır Durumu: Eğer aralık iki element arasındaki '\n\n' boşluğuna denk geldiyse:
            # En yakın önceki span'in bilgilerini devral (fallback).
            if not self.spans:
                return (1, 1, [], [])
            span_starts = [s.char_start for s in self.spans]
            idx = bisect.bisect_right(span_starts, start)
            target_span = self.spans[max(0, idx - 1)]
            return (
                target_span.page_start,
                target_span.page_end,
                list(target_span.heading_path),
                [target_span.element_type],
            )

        page_start = min(s.page_start for s in overlapping)
        page_end = max(s.page_end for s in overlapping)

        first_span = overlapping[0]
        heading_path = list(first_span.heading_path)

        # Ingestion kuralı: Bir HEADING elementinin heading_path'i kendisini içermez (ebeveynlerini içerir).
        # Ancak chunker açısından o başlığın metni o bölümün aktif başlığıdır, bu yüzden eklenir.
        if first_span.element_type == ElementType.HEADING:
            heading_text = self.text[first_span.char_start : first_span.char_end].strip()
            if not heading_path or heading_path[-1] != heading_text:
                heading_path.append(heading_text)

        # Karşılaşılan element türlerini sırasıyla ve tekilleştirerek listele (örn: [PARAGRAPH, TABLE])
        seen_types = set()
        element_types: list[ElementType] = []
        for s in overlapping:
            if s.element_type not in seen_types:
                seen_types.add(s.element_type)
                element_types.append(s.element_type)

        return page_start, page_end, heading_path, element_types


def flatten(doc: ParsedDocument) -> FlatDocument:
    """ParsedDocument içindeki yapısal elementleri tek bir metin akışına ve Span haritasına dönüştürür.

    İşleyiş Mantığı:
    1. Boş elementleri atlar.
    2. Elementleri aralarına iki yeni satır ('\\n\\n') koyarak birleştirir.
    3. Her elementin düz metindeki tam [char_start, char_end) koordinatlarını kaydeder.
    
    Matematiksel Garanti:
    FlatDocument.text[span.char_start : span.char_end] == element.text her zaman True'dur!
    """
    if not doc.elements:
        return FlatDocument(text="", spans=[], source_file=doc.source_file)

    parts: list[str] = []
    spans: list[Span] = []
    current_char = 0
    separator = "\n\n"
    sep_len = len(separator)

    for i, element in enumerate(doc.elements):
        elem_text = element.text
        if not elem_text:
            continue

        # İlk elementten sonrakilerin başına '\n\n' ayırıcı ekle
        if parts:
            parts.append(separator)
            current_char += sep_len

        elem_start = current_char
        elem_end = current_char + len(elem_text)
        parts.append(elem_text)
        current_char = elem_end

        spans.append(
            Span(
                char_start=elem_start,
                char_end=elem_end,
                element_index=i,
                element_type=element.type,
                page_start=element.page_start,
                page_end=element.page_end,
                heading_path=list(element.heading_path),
            )
        )

    full_text = "".join(parts)
    return FlatDocument(text=full_text, spans=spans, source_file=doc.source_file)
