import re                                                                                                                  
                                                                                                                               
# Terminal punctuation marks that indicate a complete sentence                                                             
TERMINAL_PUNCTUATION = {".", "!", "?", ":"}                                                                                
                                                                                                                            
                                                                                                                            
def stitch_pages(pages: list[tuple[int, str]]) -> list[tuple[str, int, int]]:                                              
    """Stitches paragraphs and tables that are broken across page boundaries.                                              
                                                                                                                            
    Args:                                                                                                                  
        pages: List of (page_number, cleaned_page_text) tuples.                                                            
                                                                                                                            
    Returns:                                                                                                               
        A list of stitched blocks as (text, page_start, page_end) tuples.                                                  
    """                                                                                                                    
    if not pages:                                                                                                          
        return []                                                                                                          
                                                                                                                            
    # Initial block representations: (text, page_start, page_end)                                                          
    blocks: list[list] = [                                                                                                 
        [text.strip(), page_num, page_num]                                                                                 
        for page_num, text in pages                                                                                        
        if text.strip()                                                                                                    
    ]                                                                                                                      
                                                                                                                            
    if len(blocks) < 2:                                                                                                    
        return [(b[0], b[1], b[2]) for b in blocks]                                                                        
                                                                                                                            
    idx = 0                                                                                                                
    while idx < len(blocks) - 1:                                                                                           
        curr_text = blocks[idx][0]                                                                                         
        next_text = blocks[idx + 1][0]                                                                                     
                                                                                                                            
        # Split current and next blocks into paragraphs                                                                    
        curr_paragraphs = [p.strip() for p in curr_text.split("\n\n") if p.strip()]                                        
        next_paragraphs = [p.strip() for p in next_text.split("\n\n") if p.strip()]                                        
                                                                                                                            
        if not curr_paragraphs or not next_paragraphs:                                                                     
            idx += 1                                                                                                       
            continue                                                                                                       
                                                                                                                            
        last_p = curr_paragraphs[-1]                                                                                       
        first_p = next_paragraphs[0]                                                                                       
                                                                                                                            
        # --- Rule 1: Paragraph Stitching ---                                                                              
        # If current page does not end with terminal punctuation                                                           
        # and next page starts with a lowercase letter or continuation:                                                    
        last_char = last_p[-1] if last_p else ""                                                                           
        first_char = first_p[0] if first_p else ""                                                                         
                                                                                                                            
        if last_char not in TERMINAL_PUNCTUATION and first_char.islower():                                                 
            # Merge incomplete paragraph from current page with beginning of next page                                     
            merged_p = f"{last_p} {first_p}"                                                                               
            curr_paragraphs[-1] = merged_p                                                                                 
            # Remove the merged first paragraph from next page                                                             
            next_paragraphs.pop(0)                                                                                         
                                                                                                                            
            blocks[idx][0] = "\n\n".join(curr_paragraphs)                                                                  
            blocks[idx][2] = blocks[idx + 1][1]  # Extend page_end                                                         
                                                                                                                            
            if next_paragraphs:                                                                                            
                blocks[idx + 1][0] = "\n\n".join(next_paragraphs)                                                          
            else:                                                                                                          
                # If next block had only that paragraph, remove it                                                         
                blocks.pop(idx + 1)                                                                                        
                continue                                                                                                   
                                                                                                                            
        # --- Rule 2: Table Header Continuation ---                                                                        
        # If current page ends with a markdown table row and next page starts                                              
        # with table rows but lacks a header separator (|---|):                                                            
        curr_lines = [l.strip() for l in blocks[idx][0].splitlines() if l.strip()]                                         
        next_lines = [l.strip() for l in blocks[idx + 1][0].splitlines() if l.strip()]                                     
                                                                                                                            
        if curr_lines and next_lines:                                                                                      
            if curr_lines[-1].startswith("|") and next_lines[0].startswith("|"):                                           
                # Check if next page table is missing a header separator (e.g. |---|)                                      
                has_separator = any("|---" in line or "|:--" in line for line in next_lines[:3])                           
                if not has_separator:                                                                                      
                    # Find table header and separator from the end of current page                                         
                    table_lines = [l for l in curr_lines if l.startswith("|")]                                             
                    if len(table_lines) >= 2:                                                                              
                        header_line = table_lines[0]                                                                       
                        sep_line = table_lines[1]                                                                          
                        # Inject header and separator to the beginning of next page's table                                
                        blocks[idx + 1][0] = f"{header_line}\n{sep_line}\n" + blocks[idx + 1][0]                           
                                                                                                                            
        idx += 1                                                                                                           
                                                                                                                            
    return [(b[0], b[1], b[2]) for b in blocks]