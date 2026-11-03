import math
from typing import Optional
from pydantic import BaseModel, Field

from app.rag.chunking.models import Chunk
from app.rag.chunking.tokenizer import Tokenizer
from app.rag.ingestion.models import ElementType, ParsedDocument


class ChunkStats(BaseModel):
    """Intrinsic metrics computed strictly from chunking output without retrieval."""
    chunk_count: int = Field(ge=0, description="Total chunks produced")
    tokens_mean: float = Field(ge=0.0, description="Mean tokens per chunk")
    tokens_p50: float = Field(ge=0.0, description="Median (50th percentile) tokens per chunk")
    tokens_p95: float = Field(ge=0.0, description="95th percentile tokens per chunk")
    tokens_min: int = Field(ge=0, description="Minimum tokens in a chunk")
    tokens_max: int = Field(ge=0, description="Maximum tokens in a chunk")
    under_min_ratio: float = Field(
        ge=0.0, le=1.0, description="Ratio of chunks with token_count < min_tokens threshold"
    )
    redundancy: float = Field(
        ge=0.0,
        description="Total chunk tokens / raw document tokens ratio (1.0 = zero overlap overhead)",
    )
    sentence_cut_ratio: float = Field(
        ge=0.0,
        le=1.0,
        description="Ratio of chunks starting with lowercase or ending without terminal punctuation",
    )
    table_split_ratio: float = Field(
        ge=0.0,
        le=1.0,
        description="Ratio of document tables that are split across multiple chunks",
    )
    table_headless_chunks: int = Field(
        ge=0,
        description="Number of table-bearing chunks lacking a header/separator row",
    )
    orphan_heading_ratio: float = Field(
        ge=0.0,
        le=1.0,
        description="Ratio of chunks ending with an isolated heading line",
    )


def _percentile(values: list[int], p: float) -> float:
    """Compute percentile using linear interpolation."""
    if not values:
        return 0.0
    sorted_v = sorted(values)
    k = (len(sorted_v) - 1) * (p / 100.0)
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return float(sorted_v[int(k)])
    d0 = sorted_v[int(f)] * (c - k)
    d1 = sorted_v[int(c)] * (k - f)
    return float(d0 + d1)


def chunk_stats(
    chunks: list[Chunk],
    doc: ParsedDocument,
    tokenizer: Tokenizer,
    min_tokens: int = 60,
) -> ChunkStats:
    """Compute intrinsic chunking quality metrics for a document and its chunks."""
    if not chunks:
        return ChunkStats(
            chunk_count=0,
            tokens_mean=0.0,
            tokens_p50=0.0,
            tokens_p95=0.0,
            tokens_min=0,
            tokens_max=0,
            under_min_ratio=0.0,
            redundancy=1.0,
            sentence_cut_ratio=0.0,
            table_split_ratio=0.0,
            table_headless_chunks=0,
            orphan_heading_ratio=0.0,
        )

    # 1. Token Dağılımı İstatistikleri
    token_counts = [c.token_count for c in chunks]
    total_chunk_tokens = sum(token_counts)
    count = len(chunks)

    tokens_mean = round(total_chunk_tokens / count, 2)
    tokens_p50 = round(_percentile(token_counts, 50), 2)
    tokens_p95 = round(_percentile(token_counts, 95), 2)
    tokens_min = min(token_counts)
    tokens_max = max(token_counts)

    under_min_count = sum(1 for t in token_counts if t < min_tokens)
    under_min_ratio = round(under_min_count / count, 4)

    # 2. Redundancy (Fazlalık / Overlap Maliyeti)
    doc_text = "\n\n".join(e.text for e in doc.elements) if doc.elements else ""
    doc_tokens = tokenizer.count(doc_text)
    if doc_tokens > 0:
        redundancy = round(total_chunk_tokens / doc_tokens, 3)
    else:
        redundancy = 1.0

    # 3. Sentence Cut Ratio (Cümle Bölünme Heuristiği)
    terminal_puncts = {".", "!", "?", "…", ":", "\"", "'", "”", "’", "|", ")", "]", "}"}

    sentence_cut_count = 0
    for c in chunks:
        stripped = c.text.strip()
        if not stripped:
            continue
        # İlk karakter küçük harf ise (cümle ortasından kesilmiş)
        starts_lower = stripped[0].islower()
        ends_terminal = stripped[-1] in terminal_puncts

        # Eğer küçük harfle başlıyorsa veya terminal noktalama/tablo ile bitmiyorsa kesilmiş say
        if starts_lower or not ends_terminal:
            sentence_cut_count += 1

    sentence_cut_ratio = round(sentence_cut_count / count, 4)

    # 4. Tablo Bölünme ve Başlıksız Parça Oranı
    table_elements = [e for e in doc.elements if e.type == ElementType.TABLE]
    total_tables = len(table_elements)
    split_tables_count = 0
    table_headless_count = 0

    if total_tables > 0:
        for t_elem in table_elements:
            t_lines = [l.strip() for l in t_elem.text.splitlines() if l.strip() and not l.startswith("|---")]
            # Bu tablonun herhangi bir satırını barındıran chunk sayısını tespit et
            containing_chunks = 0
            for c in chunks:
                if ElementType.TABLE in c.element_types or "|" in c.text:
                    if any(line in c.text for line in t_lines):
                        containing_chunks += 1

            if containing_chunks > 1:
                split_tables_count += 1

        # Başlıksız tablo parçalarını say (tablo var ama '|---|' ayırıcısı yok)
        for c in chunks:
            if ElementType.TABLE in c.element_types or "|" in c.text:
                lines = [l.strip() for l in c.text.splitlines() if l.strip()]
                table_lines = [l for l in lines if l.startswith("|") and l.endswith("|")]
                if len(table_lines) >= 2:
                    # Tablo satırları var ama 2. satır |---| ayırıcısı değilse başlıksızdır
                    has_sep = any("---" in l for l in table_lines[:2])
                    if not has_sep:
                        table_headless_count += 1

        table_split_ratio = round(split_tables_count / total_tables, 4)
    else:
        table_split_ratio = 0.0

    # 5. Yetim Başlık Oranı (Orphan Heading Ratio)
    # Chunk'ın son satırı tek başına bir başlık mı?
    orphan_heading_count = 0
    for c in chunks:
        lines = [l.strip() for l in c.text.splitlines() if l.strip()]
        if not lines:
            continue
        last_line = lines[-1]

        # Markdown başlığı veya kısa, noktasız ve büyük harfle başlayan son satır
        is_md_heading = last_line.startswith(("# ", "## ", "### ", "#### "))
        is_short_title = (
            len(last_line) <= 60
            and len(lines) > 1
            and last_line[-1] not in terminal_puncts
            and last_line[0].isupper()
        )

        if is_md_heading or is_short_title:
            orphan_heading_count += 1

    orphan_heading_ratio = round(orphan_heading_count / count, 4)

    return ChunkStats(
        chunk_count=count,
        tokens_mean=tokens_mean,
        tokens_p50=tokens_p50,
        tokens_p95=tokens_p95,
        tokens_min=tokens_min,
        tokens_max=tokens_max,
        under_min_ratio=under_min_ratio,
        redundancy=redundancy,
        sentence_cut_ratio=sentence_cut_ratio,
        table_split_ratio=table_split_ratio,
        table_headless_chunks=table_headless_count,
        orphan_heading_ratio=orphan_heading_ratio,
    )
