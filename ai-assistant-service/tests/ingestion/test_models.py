import pytest                                                                                                
from pydantic import ValidationError                                                                         
                                                                                                                
from app.rag.ingestion.models import Element, ElementType, ParsedDocument, QualityReport     


def test_element_creation_valid():
    """Valid Element instance should be created successfully."""
    element = Element(
        type=ElementType.PARAGRAPH,
        text = "This is a valid paragraph text.",
        page_start=1,
        page_end=1,
        heading_path=["Introduction"] 
    )

    assert element.type == ElementType.PARAGRAPH
    assert element.text == "This is a valid paragraph text."                                                 
    assert element.page_start == 1                                                                           
    assert element.page_end == 1                                                                             
    assert element.heading_path == ["Introduction"] 

def test_element_fails_when_page_end_smaller_than_page_start():                                              
        """Element should raise ValidationError when page_end < page_start."""                                   
        with pytest.raises(ValidationError) as exc_info:                                                         
            Element(                                                                                             
                type=ElementType.PARAGRAPH,                                                                      
                text="Invalid page range text.",                                                                 
                page_start=3,                                                                                    
                page_end=2                                                                                       
            )                                                                                                    
        assert "page_end" in str(exc_info.value)                                                                 
        assert "cannot be less than page_start" in str(exc_info.value)  

def test_element_fails_when_text_empty_or_whitespace():                                                      
        """Element should reject empty or whitespace-only text."""                                               
        with pytest.raises(ValidationError) as exc_info:                                                         
            Element(                                                                                             
                type=ElementType.PARAGRAPH,                                                                      
                text="    \n   ",                                                                                
                page_start=1,                                                                                    
                page_end=1                                                                                       
            )                                                                                                    
        assert "Element text cannot be empty" in str(exc_info.value)  

def test_element_fails_when_page_less_than_one():                                                            
        """Element should reject page numbers less than 1 (1-based index)."""                                    
        with pytest.raises(ValidationError):                                                                     
            Element(                                                                                             
                type=ElementType.PARAGRAPH,                                                                      
                text="Zero page is not allowed.",                                                                
                page_start=0,                                                                                    
                page_end=1                                                                                       
            )   

def test_parsed_document_structure():                                                                        
        """ParsedDocument should encapsulate elements and quality report correctly."""                           
        quality = QualityReport(                                                                                 
            page_count=2,                                                                                        
            empty_pages=[],                                                                                      
            suspect_char_ratio=0.0,                                                                              
            status="ok",                                                                                         
            reasons=[]                                                                                           
        )                                                                                                        
        element = Element(                                                                                       
            type=ElementType.HEADING,                                                                            
            text="Section Title",                                                                                
            page_start=1,                                                                                        
            page_end=1                                                                                           
        )                                                                                                        
        doc = ParsedDocument(                                                                                    
            source_file="terms.pdf",                                                                             
            elements=[element],                                                                                  
            quality=quality,                                                                                     
            parser_name="pymupdf4llm",                                                                           
            parser_version="2.0.0"                                                                               
        )                                                                                                        
        assert doc.source_file == "terms.pdf"                                                                    
        assert len(doc.elements) == 1                                                                            
        assert doc.quality.status == "ok" 