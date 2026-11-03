import hashlib
from app.rag.chunking.base import Chunker
from app.rag.chunking.flatten import flatten
from app.rag.chunking.models import Chunk, ChunkingConfig, ChunkStrategy
from app.rag.chunking.tokenizer import Tokenizer
from app.rag.ingestion.models import ParsedDocument


class FixedSizeChunker:
    """Sabit boyutlu kayan pencere (sliding window) chunker'ı.
    
    Tüm değerlendirmelerimiz için 'Baseline' (taban çizgisi) görevi görür.
    İçeriğe, cümlelere, paragraflara veya tablolara bakmaksızın metni
    sadece token sınırlarından katı pencerelerle dilimler.
    """

    name: str = ChunkStrategy.FIXED

    def __init__(self, tokenizer: Tokenizer, config: ChunkingConfig) -> None:
        self.tokenizer = tokenizer
        self.config = config

    def _generate_chunk_id(
        self, source_file: str, chunk_index: int, text: str
    ) -> str:
        """Deterministik ve tekrarlanabilir 16 karakterlik chunk ID üretir."""
        seed = f"{source_file}|{self.name}|{self.config.config_hash()}|{chunk_index}|{text}"
        return hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]

    def chunk(self, doc: ParsedDocument) -> list[Chunk]:
        """ParsedDocument'ı kayan pencereli sabit boyutlu chunk'lara böler."""
        flat = flatten(doc)
        if not flat.text.strip():
            return []

        # Tokenizer'dan karakter aralıkları haritasını al
        token_spans = self.tokenizer.token_spans(flat.text)
        total_tokens = len(token_spans)
        if total_tokens == 0:
            return []

        chunks: list[Chunk] = []
        chunk_idx = 0
        tok_idx = 0

        while tok_idx < total_tokens:
            # Kritik Kural: Kalan token'lar sadece bir önceki chunk'ın overlap payı kadarsa yeni chunk açma
            remaining = total_tokens - tok_idx
            if chunk_idx > 0 and remaining <= self.config.overlap_tokens:
                break

            char_start = token_spans[tok_idx][0]
            _, _, initial_heading_path, _ = flat.metadata_for(char_start, char_start + 1)

            context_prefix = ""
            prefix_tokens = 0
            if self.config.include_breadcrumb and initial_heading_path:
                context_prefix = " > ".join(initial_heading_path)
                prefix_tokens = self.tokenizer.count(context_prefix)

            # Adil bağlam bütçesi: context_prefix varsa max_tokens'tan düş
            budget = max(1, self.config.max_tokens - prefix_tokens)
            step = max(1, budget - self.config.overlap_tokens)

            window_end = min(tok_idx + budget, total_tokens)
            char_end = token_spans[window_end - 1][1]

            chunk_text = flat.text[char_start:char_end]
            token_count = window_end - tok_idx

            # Düz metin haritasından sayfa, başlık ve element türlerini çek
            page_start, page_end, heading_path, element_types = flat.metadata_for(
                char_start, char_end
            )

            if not context_prefix and self.config.include_breadcrumb and heading_path:
                context_prefix = " > ".join(heading_path)

            chunk_id = self._generate_chunk_id(doc.source_file, chunk_idx, chunk_text)

            chunks.append(
                Chunk(
                    id=chunk_id,
                    strategy=ChunkStrategy.FIXED,
                    source_file=doc.source_file,
                    chunk_index=chunk_idx,
                    text=chunk_text,
                    context_prefix=context_prefix,
                    token_count=token_count,
                    page_start=page_start,
                    page_end=page_end,
                    heading_path=heading_path,
                    element_types=element_types,
                    char_start=char_start,
                    char_end=char_end,
                )
            )

            chunk_idx += 1
            tok_idx += step

        return chunks
