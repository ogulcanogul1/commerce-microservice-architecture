import importlib.metadata
from pathlib import Path
import pymupdf4llm

from app.rag.ingestion.models import ParsedDocument
from app.rag.ingestion.pdf.cleaning import dehyphenate, normalize, remove_repeated_lines
from app.rag.ingestion.pdf.elements import parse_markdown_to_elements
from app.rag.ingestion.pdf.quality import build_report
from app.rag.ingestion.pdf.stitching import stitch_pages
from app.rag.ingestion.pdf.triage import find_empty_pages, page_char_counts


class PDFLoader:
    """PDF Document Loader that extracts, cleans, stitches, and structures PDF documents.

    Implements the DocumentLoader protocol.
    """

    PARSER_NAME: str = "pymupdf4llm"

    def __init__(self) -> None:
        try:
            self._parser_version = getattr(
                pymupdf4llm, "__version__", importlib.metadata.version("pymupdf4llm")
            )
        except Exception:
            self._parser_version = "2.0"

    def load_clean_pages(self, path: Path | str) -> list[tuple[int, str]]:
        """Parses a PDF into cleaned markdown text per page.

        Steps:
        1. Validates file existence.
        2. Runs triage to detect empty/scanned pages.
        3. Calls pymupdf4llm.to_markdown(..., page_chunks=True) to extract markdown pages.
        4. Cleans repeated headers/footers, hyphenation, and normalizes unicode/newlines.
        5. Returns a list of (page_number, cleaned_text) pairs.

        Args:
            path: Path to the target PDF file.

        Returns:
            List of tuples where each tuple contains (1-based page number, cleaned markdown text).

        Raises:
            FileNotFoundError: If the PDF file does not exist.
        """
        file_path = Path(path)
        if not file_path.exists():
            raise FileNotFoundError(f"PDF file not found at: {file_path}")

        # 1. Triage inspection
        char_counts = page_char_counts(file_path)
        _empty_pages = find_empty_pages(char_counts)

        # 2. Extract page chunks as Markdown using pymupdf4llm
        chunks = pymupdf4llm.to_markdown(str(file_path), page_chunks=True)
        raw_pages: list[str] = [chunk.get("text", "") for chunk in chunks]

        # 3. Pipeline Step A: Remove cross-page repeating headers & footers
        no_repeat_pages = remove_repeated_lines(raw_pages)

        # 4. Pipeline Step B: Dehyphenate and normalize each page
        cleaned_pages: list[tuple[int, str]] = []
        for idx, text in enumerate(no_repeat_pages):
            page_num = idx + 1
            if idx < len(chunks):
                meta_page = chunks[idx].get("metadata", {}).get("page_number")
                if meta_page is not None:
                    page_num = int(meta_page)

            clean_text = normalize(dehyphenate(text))
            cleaned_pages.append((page_num, clean_text))

        return cleaned_pages

    def load(self, path: Path | str) -> ParsedDocument:
        """Parses a PDF into a fully structured, quality-assessed ParsedDocument.

        Pipeline Stages:
        1. Validation & Triage (detect empty/scanned pages)
        2. Markdown Extraction & Text Cleaning (headers/footers, hyphenation, normalization)
        3. Cross-page Stitching (broken sentences and tables)
        4. Element Parsing (typed Element objects with heading breadcrumb paths)
        5. Quality Assessment (health evaluation and quarantine checks)
        6. Encapsulation into ParsedDocument

        Args:
            path: Path to the target PDF file.

        Returns:
            A ParsedDocument containing all extracted elements and quality report.

        Raises:
            FileNotFoundError: If the file does not exist.
        """
        file_path = Path(path)
        if not file_path.exists():
            raise FileNotFoundError(f"PDF file not found at: {file_path}")

        # Stage 1: Triage
        char_counts = page_char_counts(file_path)
        page_count = len(char_counts)
        empty_pages = find_empty_pages(char_counts)

        # Stage 2: Extract & Clean Pages
        clean_pages = self.load_clean_pages(file_path)

        # Stage 3: Stitch cross-page boundaries
        stitched_blocks = stitch_pages(clean_pages)

        # Stage 4: Structure into Elements with heading paths
        elements = parse_markdown_to_elements(stitched_blocks)

        # Stage 5: Evaluate Quality
        full_text = " ".join(element.text for element in elements)
        quality = build_report(
            page_count=page_count,
            empty_pages=empty_pages,
            full_text=full_text,
        )

        # Stage 6: Return complete ParsedDocument
        return ParsedDocument(
            source_file=file_path.name,
            elements=elements,
            quality=quality,
            parser_name=self.PARSER_NAME,
            parser_version=self._parser_version,
        )
