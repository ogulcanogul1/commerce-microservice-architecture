import hashlib
import logging
import re
from dataclasses import dataclass
from typing import Optional

from app.rag.chunking.base import Chunker
from app.rag.chunking.flatten import flatten
from app.rag.chunking.models import Chunk, ChunkingConfig, ChunkStrategy
from app.rag.chunking.sentences import split_sentences
from app.rag.chunking.tokenizer import Tokenizer
from app.rag.ingestion.models import Element, ElementType, ParsedDocument

logger = logging.getLogger(__name__)


@dataclass
class _Section:
    heading_path: list[str]
    elements: list[tuple[int, Element]]  # (original_element_index, Element)
    heading_element: Optional[tuple[int, Element]] = None


class StructureAwareChunker:
    """Belge yapısını (başlık hiyerarşisi, tablolar, listeler) koruyan akıllı chunker.

    Kurallar:
    1. Bölümleme: Her HEADING yeni bir bölüm başlatır; chunk'lar bölüm sınırlarını aşmaz.
    2. Bütçe: context_prefix embedding bütçesinden düşülür (max_tokens - prefix_tokens).
    3. Tablo Sürekliliği: Bütçeyi aşan tablolarda başlık ve ayırıcı (|---|) sonraki parçalara da kopyalanır.
    4. Kardeş Bölüm Birleştirme: min_tokens altındaki bölümler aynı üst başlığa sahipse birleştirilir.
    5. Yetim Başlık Önleme: Başlıklar asla tek başına yalnız bir chunk oluşturmaz.
    """

    name: str = ChunkStrategy.STRUCTURE

    def __init__(self, tokenizer: Tokenizer, config: ChunkingConfig) -> None:
        self.tokenizer = tokenizer
        self.config = config

    def _generate_chunk_id(
        self, source_file: str, chunk_index: int, text: str
    ) -> str:
        """Deterministik ve tekrarlanabilir 16 karakterlik chunk ID üretir."""
        seed = f"{source_file}|{self.name}|{self.config.config_hash()}|{chunk_index}|{text}"
        return hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]

    def _split_table(self, table_text: str, budget: int) -> list[str]:
        """Bütçeyi aşan tabloyu satırlara böler. Başlık ve ayırıcı satırı her parçaya ekler."""
        lines = [line for line in table_text.splitlines() if line.strip()]
        if len(lines) <= 2:
            return [table_text]

        header = lines[0]
        separator = lines[1]
        header_block = f"{header}\n{separator}\n"
        header_tokens = self.tokenizer.count(header_block)

        effective_budget = budget - header_tokens
        if effective_budget <= 0:
            logger.warning("Tablo başlığı tek başına token bütçesini aşıyor.")
            return [table_text]

        chunks: list[str] = []
        current_rows: list[str] = []

        for row in lines[2:]:
            row_tokens = self.tokenizer.count(row)
            test_rows = current_rows + [row]
            test_content = header_block + "\n".join(test_rows)

            if self.tokenizer.count(test_content) <= budget:
                current_rows.append(row)
            else:
                if current_rows:
                    chunks.append(header_block + "\n".join(current_rows))
                    current_rows = [row]
                else:
                    # Tek satır bile bütçeyi aşıyorsa mecburen olduğu gibi ekle
                    chunks.append(header_block + row)
                    current_rows = []

        if current_rows:
            chunks.append(header_block + "\n".join(current_rows))

        return chunks

    def _split_list(self, list_text: str, budget: int) -> list[str]:
        """Bütçeyi aşan listeyi madde sınırlarından böler."""
        items = re.split(r"(?m)^(?=[\*\-\+]|\d+\.)", list_text)
        items = [it.strip() for it in items if it.strip()]
        if len(items) <= 1:
            return self._split_paragraph(list_text, budget)

        chunks: list[str] = []
        current_items: list[str] = []

        for item in items:
            test_items = current_items + [item]
            test_text = "\n".join(test_items)
            if self.tokenizer.count(test_text) <= budget:
                current_items.append(item)
            else:
                if current_items:
                    chunks.append("\n".join(current_items))
                    current_items = [item]
                else:
                    chunks.extend(self._split_paragraph(item, budget))
                    current_items = []

        if current_items:
            chunks.append("\n".join(current_items))

        return chunks

    def _split_paragraph(self, text: str, budget: int) -> list[str]:
        """Bütçeyi aşan paragrafı recursive olarak cümle ve kelime sınırlarından böler."""
        if self.tokenizer.count(text) <= budget:
            return [text]

        # 1. Cümlelere göre dene
        sent_spans = split_sentences(text)
        if len(sent_spans) > 1:
            sentences = [text[s:e].strip() for s, e in sent_spans if text[s:e].strip()]
            chunks: list[str] = []
            curr: list[str] = []
            for s in sentences:
                cand = " ".join(curr + [s])
                if self.tokenizer.count(cand) <= budget:
                    curr.append(s)
                else:
                    if curr:
                        chunks.append(" ".join(curr))
                        curr = [s]
                    else:
                        chunks.extend(self._split_paragraph(s, budget))
                        curr = []
            if curr:
                chunks.append(" ".join(curr))
            return chunks

        # 2. Cümle de sığmıyorsa kelimelere göre böl
        words = text.split()
        chunks = []
        curr = []
        for w in words:
            cand = " ".join(curr + [w])
            if self.tokenizer.count(cand) <= budget:
                curr.append(w)
            else:
                if curr:
                    chunks.append(" ".join(curr))
                    curr = [w]
                else:
                    # Tek bir kelime bile bütçeden büyükse mecburen ekle
                    chunks.append(w)
                    curr = []
        if curr:
            chunks.append(" ".join(curr))
        return chunks

    def _build_sections(self, elements: list[Element]) -> list[_Section]:
        """Elementleri HEADING elementlerine göre hiyerarşik bölümlere ayırır."""
        sections: list[_Section] = []
        current_section = _Section(heading_path=[], elements=[])

        for idx, elem in enumerate(elements):
            if elem.type == ElementType.HEADING:
                # Yeni bir başlık geldiğinde önceki bölüm doluysa kaydet
                if current_section.elements or current_section.heading_element:
                    sections.append(current_section)

                # Ingestion kuralı: HEADING'in heading_path'i kendisini içermez,
                # bu bölümün aktif yolu için başlığın kendi metnini ekleriz.
                path = list(elem.heading_path)
                heading_text = elem.text.strip()
                if not path or path[-1] != heading_text:
                    path.append(heading_text)

                current_section = _Section(
                    heading_path=path,
                    elements=[],
                    heading_element=(idx, elem),
                )
            else:
                current_section.elements.append((idx, elem))

        if current_section.elements or current_section.heading_element:
            sections.append(current_section)

        # Yetim başlık (orphan heading) yönetimi:
        # İçeriği olmayan bir başlık varsa sonraki bölümle birleştir
        consolidated: list[_Section] = []
        orphan_heading: Optional[tuple[int, Element]] = None

        for sec in sections:
            if not sec.elements and sec.heading_element:
                orphan_heading = sec.heading_element
                continue
            if orphan_heading:
                # Önceki yetim başlığı bu bölümün başına ekle
                sec.elements.insert(0, orphan_heading)
                orphan_heading = None
            consolidated.append(sec)

        return consolidated

    def _merge_small_sections(self, sections: list[_Section]) -> list[_Section]:
        """min_tokens'tan küçük bölümleri aynı üst başlığa ait sonraki kardeş bölümle birleştirir."""
        if len(sections) <= 1:
            return sections

        merged: list[_Section] = []
        i = 0
        while i < len(sections):
            sec = sections[i]
            # Bölümün toplam token sayısını hesapla
            total_sec_text = " ".join(
                [e.text for _, e in sec.elements]
                + ([sec.heading_element[1].text] if sec.heading_element else [])
            )
            sec_tokens = self.tokenizer.count(total_sec_text)

            if sec_tokens < self.config.min_tokens and i + 1 < len(sections):
                next_sec = sections[i + 1]
                # Aynı üst başlığa (parent) mı sahipler?
                parent_curr = sec.heading_path[:-1] if len(sec.heading_path) > 1 else []
                parent_next = (
                    next_sec.heading_path[:-1] if len(next_sec.heading_path) > 1 else []
                )

                if parent_curr == parent_next and parent_curr:
                    next_text = " ".join([e.text for _, e in next_sec.elements])
                    if self.tokenizer.count(total_sec_text + " " + next_text) <= self.config.max_tokens:
                        # Birleştir
                        combined_elements = []
                        if sec.heading_element:
                            combined_elements.append(sec.heading_element)
                        combined_elements.extend(sec.elements)
                        if next_sec.heading_element:
                            combined_elements.append(next_sec.heading_element)
                        combined_elements.extend(next_sec.elements)

                        combined_sec = _Section(
                            heading_path=parent_curr,
                            elements=combined_elements,
                            heading_element=None,
                        )
                        merged.append(combined_sec)
                        i += 2
                        continue

            merged.append(sec)
            i += 1

        return merged

    def chunk(self, doc: ParsedDocument) -> list[Chunk]:
        """ParsedDocument'ı yapıya saygılı (Structure-Aware) chunk'lara böler."""
        if not doc.elements:
            return []

        flat = flatten(doc)
        sections = self._build_sections(doc.elements)
        sections = self._merge_small_sections(sections)

        raw_chunks: list[dict] = []

        for sec in sections:
            prefix = ""
            if self.config.include_breadcrumb and sec.heading_path:
                prefix = " > ".join(sec.heading_path)

            prefix_tokens = self.tokenizer.count(prefix) if prefix else 0
            budget = max(1, self.config.max_tokens - prefix_tokens)

            # Bu bölümdeki paketlenecek tüm element birimleri
            items_to_pack: list[tuple[int, Element]] = []
            if sec.heading_element:
                items_to_pack.append(sec.heading_element)
            items_to_pack.extend(sec.elements)

            current_chunk_parts: list[str] = []
            current_elem_indices: list[int] = []

            def flush_current_chunk():
                nonlocal current_chunk_parts, current_elem_indices
                if not current_chunk_parts:
                    return
                text = "\n\n".join(current_chunk_parts)
                raw_chunks.append(
                    {
                        "text": text,
                        "context_prefix": prefix,
                        "heading_path": sec.heading_path,
                        "element_indices": list(current_elem_indices),
                    }
                )
                current_chunk_parts = []
                current_elem_indices = []

            for elem_idx, elem in items_to_pack:
                # Tablo izolasyonu isteniyorsa
                if elem.type == ElementType.TABLE and self.config.isolate_tables:
                    flush_current_chunk()
                    sub_tables = self._split_table(elem.text, budget)
                    for st in sub_tables:
                        raw_chunks.append(
                            {
                                "text": st,
                                "context_prefix": prefix,
                                "heading_path": sec.heading_path,
                                "element_indices": [elem_idx],
                            }
                        )
                    continue

                elem_tokens = self.tokenizer.count(elem.text)

                # Eğer element tek başına bütçeyi aşıyorsa
                if elem_tokens > budget:
                    flush_current_chunk()
                    if elem.type == ElementType.TABLE:
                        sub_parts = self._split_table(elem.text, budget)
                    elif elem.type == ElementType.LIST:
                        sub_parts = self._split_list(elem.text, budget)
                    else:
                        sub_parts = self._split_paragraph(elem.text, budget)

                    for sp in sub_parts:
                        raw_chunks.append(
                            {
                                "text": sp,
                                "context_prefix": prefix,
                                "heading_path": sec.heading_path,
                                "element_indices": [elem_idx],
                            }
                        )
                    continue

                # Element sığıyor mu kontrol et
                cand_parts = current_chunk_parts + [elem.text]
                cand_text = "\n\n".join(cand_parts)
                if self.tokenizer.count(cand_text) <= budget:
                    current_chunk_parts.append(elem.text)
                    current_elem_indices.append(elem_idx)
                else:
                    flush_current_chunk()
                    current_chunk_parts = [elem.text]
                    current_elem_indices = [elem_idx]

            flush_current_chunk()

        # Nihai Chunk modellerini üret
        final_chunks: list[Chunk] = []
        for idx, rc in enumerate(raw_chunks):
            chunk_text = rc["text"]
            elem_indices = rc["element_indices"]

            # Metadata'yı FlatDocument span'lerinden ve elementlerden hesapla
            matching_spans = [
                s for s in flat.spans if s.element_index in elem_indices
            ]

            if matching_spans:
                char_start = min(s.char_start for s in matching_spans)
                char_end = max(s.char_end for s in matching_spans)
                page_start = min(s.page_start for s in matching_spans)
                page_end = max(s.page_end for s in matching_spans)
                element_types = []
                seen_t = set()
                for s in matching_spans:
                    if s.element_type not in seen_t:
                        seen_t.add(s.element_type)
                        element_types.append(s.element_type)
            else:
                char_start = 0
                char_end = len(chunk_text)
                page_start = 1
                page_end = 1
                element_types = [ElementType.PARAGRAPH]

            chunk_id = self._generate_chunk_id(doc.source_file, idx, chunk_text)

            final_chunks.append(
                Chunk(
                    id=chunk_id,
                    strategy=ChunkStrategy.STRUCTURE,
                    source_file=doc.source_file,
                    chunk_index=idx,
                    text=chunk_text,
                    context_prefix=rc["context_prefix"],
                    token_count=self.tokenizer.count(chunk_text),
                    page_start=page_start,
                    page_end=page_end,
                    heading_path=rc["heading_path"],
                    element_types=element_types,
                    char_start=char_start,
                    char_end=char_end,
                )
            )

        return final_chunks
