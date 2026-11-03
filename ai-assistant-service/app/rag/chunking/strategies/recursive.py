import hashlib
import re
from app.rag.chunking.base import Chunker
from app.rag.chunking.flatten import flatten
from app.rag.chunking.models import Chunk, ChunkingConfig, ChunkStrategy
from app.rag.chunking.sentences import split_sentences
from app.rag.chunking.tokenizer import Tokenizer
from app.rag.ingestion.models import ParsedDocument


class RecursiveChunker:
    """Recursive (özyinelemeli) Chunker.

    Separator merdiveni:
    1. '\\n\\n' (Paragraflar)
    2. '\\n' (Satırlar)
    3. Cümleler (split_sentences ile Türkçe korumalı)
    4. ' ' (Kelimeler)
    5. Token düzeyi zorla dilimleme

    Metni anlamlı semantik sınırlara saygı göstererek atomik birimlere ayırır,
    ardından greedy (açgözlü) paketleme ve tam birim örtüşmesi (overlap) ile chunk'lar üretir.
    """

    name: str = ChunkStrategy.RECURSIVE

    def __init__(self, tokenizer: Tokenizer, config: ChunkingConfig) -> None:
        self.tokenizer = tokenizer
        self.config = config

    def _generate_chunk_id(
        self, source_file: str, chunk_index: int, text: str
    ) -> str:
        """Deterministik ve tekrarlanabilir 16 karakterlik chunk ID üretir."""
        seed = f"{source_file}|{self.name}|{self.config.config_hash()}|{chunk_index}|{text}"
        return hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]

    def _split_by_separator(
        self, text: str, start: int, end: int, separator_re: re.Pattern
    ) -> list[tuple[int, int]]:
        """Verilen regex ayırıcıya göre [start, end) aralığını dilimler.
        Separator bir önceki parçanın sonuna eklenir (kapsama garantisi).
        """
        sub_text = text[start:end]
        matches = list(separator_re.finditer(sub_text))
        if not matches:
            return [(start, end)]

        spans: list[tuple[int, int]] = []
        curr = start
        for match in matches:
            part_end = start + match.end()
            if part_end > curr:
                spans.append((curr, part_end))
                curr = part_end

        if curr < end:
            spans.append((curr, end))

        return spans

    def _get_atomic_units(
        self, text: str, start: int, end: int, level: int = 0
    ) -> list[tuple[int, int]]:
        """Aralığı özyinelemeli olarak max_tokens limitine sığan atomik birimlere böler."""
        if start >= end:
            return []

        slice_text = text[start:end]
        token_count = self.tokenizer.count(slice_text)

        # Eğer parça zaten max_tokens bütçesine sığıyorsa daha fazla bölme
        if token_count <= self.config.max_tokens:
            return [(start, end)]

        # Seviye 4: En dip seviye - Token düzeyinde zorla pencerelere böl
        if level >= 4:
            spans = self.tokenizer.token_spans(slice_text)
            if not spans:
                return [(start, end)]
            units: list[tuple[int, int]] = []
            for i in range(0, len(spans), self.config.max_tokens):
                tok_chunk = spans[i : i + self.config.max_tokens]
                unit_start = start + tok_chunk[0][0]
                unit_end = start + tok_chunk[-1][1]
                units.append((unit_start, unit_end))
            return units

        # Seviyeler: 0: "\n\n", 1: "\n", 2: sentences, 3: " "
        parts: list[tuple[int, int]] = []
        if level == 0:
            parts = self._split_by_separator(text, start, end, re.compile(r"\n\n+"))
        elif level == 1:
            parts = self._split_by_separator(text, start, end, re.compile(r"\n+"))
        elif level == 2:
            sent_spans = split_sentences(slice_text)
            if len(sent_spans) > 1:
                parts = [(start + s, start + e) for s, e in sent_spans]
            else:
                parts = [(start, end)]
        elif level == 3:
            parts = self._split_by_separator(text, start, end, re.compile(r"\s+"))

        # Eğer bu seviyede hiç bölünemediyse doğrudan bir alt seviyeye geç
        if len(parts) <= 1:
            return self._get_atomic_units(text, start, end, level=level + 1)

        # Bölünen her parçayı incele ve sığmayanları bir alt seviyede özyinele
        all_units: list[tuple[int, int]] = []
        for p_start, p_end in parts:
            p_units = self._get_atomic_units(text, p_start, p_end, level=level + 1)
            all_units.extend(p_units)

        return all_units

    def chunk(self, doc: ParsedDocument) -> list[Chunk]:
        """ParsedDocument'ı recursive separator merdiveniyle chunk'lara böler."""
        flat = flatten(doc)
        if not flat.text.strip():
            return []

        # 1. Metni max_tokens'ı aşmayan atomik birimlere ayır
        units = self._get_atomic_units(flat.text, 0, len(flat.text), level=0)
        if not units:
            return []

        # 2. Greedy paketleme ve overlap ile chunk'ları oluştur
        chunk_spans: list[tuple[int, int]] = []
        current_units: list[tuple[int, int]] = []

        for unit in units:
            candidate_units = current_units + [unit]
            cand_start = candidate_units[0][0]
            cand_end = candidate_units[-1][1]
            cand_token_count = self.tokenizer.count(flat.text[cand_start:cand_end])

            if cand_token_count <= self.config.max_tokens:
                current_units.append(unit)
            else:
                # Mevcut birikmiş chunk'ı kapat
                if current_units:
                    chunk_spans.append((current_units[0][0], current_units[-1][1]))

                    # Overlap: Önceki chunk'ın sonundaki tam birimleri geriye doğru topla
                    overlap_units: list[tuple[int, int]] = []
                    for u in reversed(current_units):
                        test_overlap = [u] + overlap_units
                        ov_text = flat.text[test_overlap[0][0] : test_overlap[-1][1]]
                        if self.tokenizer.count(ov_text) <= self.config.overlap_tokens:
                            overlap_units.insert(0, u)
                        else:
                            break

                    # Overlap birimleri + yeni gelen unit max_tokens'ı aşıyor mu?
                    # Aşıyorsa overlap birimlerini azalt
                    while overlap_units:
                        test_cand = overlap_units + [unit]
                        test_text = flat.text[test_cand[0][0] : test_cand[-1][1]]
                        if self.tokenizer.count(test_text) <= self.config.max_tokens:
                            break
                        overlap_units.pop(0)

                    current_units = overlap_units + [unit]
                else:
                    current_units = [unit]

        if current_units:
            chunk_spans.append((current_units[0][0], current_units[-1][1]))

        # 3. Son chunk min_tokens'tan küçükse ve öncekiyle birleşince max_tokens'ı aşmıyorsa birleştir
        if len(chunk_spans) > 1:
            last_start, last_end = chunk_spans[-1]
            last_tokens = self.tokenizer.count(flat.text[last_start:last_end])
            if last_tokens < self.config.min_tokens:
                prev_start, _ = chunk_spans[-2]
                merged_text = flat.text[prev_start:last_end]
                if self.tokenizer.count(merged_text) <= self.config.max_tokens:
                    chunk_spans.pop()
                    chunk_spans[-1] = (prev_start, last_end)

        # 4. Chunk nesnelerini üret
        chunks: list[Chunk] = []
        for idx, (c_start, c_end) in enumerate(chunk_spans):
            chunk_text = flat.text[c_start:c_end]

            # Chunk sonundaki gereksiz satır sonlarını ve boşlukları kırp
            trailing_ws = len(chunk_text) - len(chunk_text.rstrip())
            if trailing_ws > 0:
                c_end = c_end - trailing_ws
                chunk_text = chunk_text.rstrip()

            token_count = self.tokenizer.count(chunk_text)
            page_start, page_end, heading_path, element_types = flat.metadata_for(
                c_start, c_end
            )

            context_prefix = ""
            if self.config.include_breadcrumb and heading_path:
                context_prefix = " > ".join(heading_path)

            chunk_id = self._generate_chunk_id(doc.source_file, idx, chunk_text)

            chunks.append(
                Chunk(
                    id=chunk_id,
                    strategy=ChunkStrategy.RECURSIVE,
                    source_file=doc.source_file,
                    chunk_index=idx,
                    text=chunk_text,
                    context_prefix=context_prefix,
                    token_count=token_count,
                    page_start=page_start,
                    page_end=page_end,
                    heading_path=heading_path,
                    element_types=element_types,
                    char_start=c_start,
                    char_end=c_end,
                )
            )

        return chunks
