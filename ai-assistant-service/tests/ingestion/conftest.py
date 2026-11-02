from pathlib import Path                                                                                     
import pytest                                                                                                
import pymupdf                                                                                               
                                                                                                                
                                                                                                                
@pytest.fixture                                                                                              
def two_column_pdf(tmp_path: Path) -> Path:                                                                  
    """Creates a single-page PDF with two distinct text columns."""                                          
    pdf_path = tmp_path / "two_column.pdf"                                                                   
    doc = pymupdf.open()                                                                                     
    page = doc.new_page(width=595, height=842)  # Standard A4 size                                           
                                                                                                                
    # Left column: (x0, y0, x1, y1)                                                                          
    left_rect = pymupdf.Rect(50, 50, 270, 750)                                                               
    page.insert_textbox(                                                                                     
        left_rect,                                                                                           
        "Left Column Title\n\nThis is paragraph one in the left column. "                                    
        "It contains content that stays strictly on the left side."                                          
    )                                                                                                        
                                                                                                                
    # Right column                                                                                           
    right_rect = pymupdf.Rect(320, 50, 540, 750)                                                             
    page.insert_textbox(                                                                                     
        right_rect,                                                                                          
        "Right Column Title\n\nThis is paragraph two in the right column. "                                  
        "It contains content that stays strictly on the right side."                                         
    )                                                                                                        
                                                                                                                
    doc.save(str(pdf_path))                                                                                  
    doc.close()                                                                                              
    return pdf_path                                                                                          
                                                                                                                
                                                                                                                
@pytest.fixture                                                                                              
def cross_page_pdf(tmp_path: Path) -> Path:                                                                  
    """Creates a 2-page PDF containing cross-page split paragraphs, tables, and headers/footers."""          
    pdf_path = tmp_path / "cross_page.pdf"                                                                   
    doc = pymupdf.open()                                                                                     
                                                                                                                
    # --- Page 1 ---                                                                                         
    page1 = doc.new_page(width=595, height=842)                                                              
    # Header & Footer                                                                                        
    page1.insert_text((50, 40), "Kuzey Market Politika Kılavuzu", fontsize=10)                               
    page1.insert_text((270, 810), "Sayfa 1", fontsize=10)                                                    
                                                                                                                
    # Content with hyphenation and incomplete sentence at page end                                           
    body1 = (                                                                                                
        "# 1. Iade Kosullari\n\n"                                                                            
        "Musteri memnuniyeti sirketimizce karsı-\n"                                                          
        "lanır ve iade sureci titizlikle yurutulur.\n\n"                                                     
        "Iade islemlerinde kargo gonderim bedeli musteri tarafindan"                                         
    )                                                                                                        
    page1.insert_textbox(pymupdf.Rect(50, 70, 540, 600), body1)                                              
                                                                                                                
    # Table start at the bottom of Page 1                                                                    
    table_p1 = (                                                                                             
        "| Urun Grubu | Garanti Suresi |\n"                                                                  
        "|---|---|\n"                                                                                        
        "| Elektronik | 2 Yil |"                                                                             
    )                                                                                                        
    page1.insert_textbox(pymupdf.Rect(50, 620, 540, 780), table_p1)                                          
                                                                                                                
    # --- Page 2 ---                                                                                         
    page2 = doc.new_page(width=595, height=842)                                                              
    # Header & Footer                                                                                        
    page2.insert_text((50, 40), "Kuzey Market Politika Kılavuzu", fontsize=10)                               
    page2.insert_text((270, 810), "Sayfa 2", fontsize=10)                                                    
                                                                                                                
    # Sentence completion starting with lowercase                                                            
    body2 = (                                                                                                
        "odenir ve depoya ulasinca incelenir.\n\n"                                                           
        "## 2. Diger Hukuklar\n\n"                                                                           
        "Musteriler cayma hakkina sahiptir."                                                                 
    )                                                                                                        
    page2.insert_textbox(pymupdf.Rect(50, 70, 540, 400), body2)                                              
                                                                                                                
    # Table continuation without markdown header separator                                                   
    table_p2 = (                                                                                             
        "| Beyaz Esya | 3 Yil |\n"                                                                           
        "| Mobilya | 1 Yil |"                                                                                
    )                                                                                                        
    page2.insert_textbox(pymupdf.Rect(50, 420, 540, 600), table_p2)                                          
                                                                                                                
    doc.save(str(pdf_path))                                                                                  
    doc.close()                                                                                              
    return pdf_path                                                                                          
                                                                                                                
                                                                                                                
@pytest.fixture                                                                                              
def scanned_like_pdf(tmp_path: Path) -> Path:                                                                
    """Creates a single-page PDF with no selectable text (simulating a scanned image)."""                    
    pdf_path = tmp_path / "scanned_like.pdf"                                                                 
    doc = pymupdf.open()                                                                                     
    page = doc.new_page(width=595, height=842)                                                               
                                                                                                                
    # Draw shapes instead of text (no text layer)                                                            
    shape_rect = pymupdf.Rect(100, 100, 450, 600)                                                            
    page.draw_rect(shape_rect, color=(0.2, 0.4, 0.6), fill=(0.9, 0.9, 0.9), width=2)                         
    page.draw_line(pymupdf.Point(100, 100), pymupdf.Point(450, 600), color=(0.8, 0.2, 0.2))                  
                                                                                                                
    doc.save(str(pdf_path))                                                                                  
    doc.close()                                                                                              
    return pdf_path