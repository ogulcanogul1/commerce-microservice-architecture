from pathlib import Path
import pymupdf4llm

from app.rag.ingestion.pdf.cleaning import dehyphenate, normalize, remove_repeated_lines
from app.rag.ingestion.pdf.triage import find_empty_pages, page_char_counts


class PDFLoader:
    """PDF Document Loader that extracts and cleans markdown page text.""" 
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
                                                                                                                               
            # 1. Triage inspection (kept for QualityReport in later steps)                                                     
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
                # Read 1-based page number from pymupdf4llm metadata if available                                              
                if idx < len(chunks):                                                                                          
                    meta_page = chunks[idx].get("metadata", {}).get("page_number")                                             
                    if meta_page is not None:                                                                                  
                        page_num = int(meta_page)                                                                              
                                                                                                                               
                clean_text = normalize(dehyphenate(text))                                                                      
                cleaned_pages.append((page_num, clean_text))                                                                   
                                                                                                                               
            return cleaned_pages