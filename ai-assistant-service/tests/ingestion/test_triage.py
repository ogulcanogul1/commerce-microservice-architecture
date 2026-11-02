from pathlib import Path                                                                                     
                                                                                                                
from app.rag.ingestion.pdf.triage import find_empty_pages, page_char_counts                                  
                                                                                                                
                                                                                                                
def test_triage_detects_scanned_page_as_empty(scanned_like_pdf: Path):                                       
    """Scanned-like page has 0 characters and must be detected as empty (page 1)."""                         
    counts = page_char_counts(scanned_like_pdf)                                                              
    assert counts == [0]                                                                                     
    empty_pages = find_empty_pages(counts, min_chars=50)                                                     
    assert empty_pages == [1]                                                                                
                                                                                                                
                                                                                                                
def test_triage_detects_two_column_as_non_empty(two_column_pdf: Path):                                       
    """Two-column document contains substantial text and should have no empty pages."""                      
    counts = page_char_counts(two_column_pdf)                                                                
    assert len(counts) == 1                                                                                  
    assert counts[0] > 50                                                                                    
    empty_pages = find_empty_pages(counts, min_chars=50)                                                     
    assert empty_pages == []