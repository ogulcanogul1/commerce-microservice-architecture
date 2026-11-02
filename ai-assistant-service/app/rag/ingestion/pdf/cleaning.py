import re                                                                                                    
import unicodedata                                                                                           
from collections import Counter   

def dehyphenate(text: str) -> str:                                                                           
        """Merges words broken across lines by a hyphen while preserving hyphenated words.                       
                                                                                                                 
        Example:                                                                                                 
            'karşı-\\nlanır' -> 'karşılanır'                                                                     
            'e-ticaret' -> 'e-ticaret'                                                                           
        """                                                                                                      
        # Pattern: a word character followed by a hyphen, optional space, and a newline,                         
        # then followed by the continuation word character.                                                      
        pattern = r"([^\W\d_])-[\r\n]+([^\W\d_])"                                                                
        return re.sub(pattern, r"\1\2", text)

def normalize(text: str) -> str:                                                                             
        """Normalizes Unicode text to NFC format and collapses multiple blank lines."""                          
        normalized = unicodedata.normalize("NFC", text)                                                          
        # Collapse 3 or more consecutive newlines into 2 (standard Markdown paragraph spacing)                   
        collapsed = re.sub(r"\n{3,}", "\n\n", normalized)                                                        
        return collapsed.strip()


def remove_repeated_lines(pages: list[str]) -> list[str]:                                                    
        """Detects and removes repeating headers and footers across pages.                                       
                                                                                                                 
        Replaces digits with '#' to match patterns like 'Page 1' and 'Page 2' as 'Page #'.                       
        Lines that appear in at least max(2, 0.6 * page_count) pages are removed.                                
        """                                                                                                      
        if len(pages) < 2:                                                                                       
            return pages                                                                                         
                                                                                                                 
        threshold = max(2, int(0.6 * len(pages)))                                                                
                                                                                                                 
        def line_pattern(line: str) -> str:                                                                      
            # Normalize digits to '#' and strip whitespace                                                       
            return re.sub(r"\d+", "#", line.strip())                                                             
                                                                                                                 
        # Count pattern occurrences across distinct pages                                                        
        pattern_page_counts: Counter[str] = Counter()                                                            
        for page_text in pages:                                                                                  
            seen_in_this_page: set[str] = set()                                                                  
            for line in page_text.splitlines():                                                                  
                clean = line.strip()                                                                             
                if not clean:                                                                                    
                    continue                                                                                     
                pattern = line_pattern(clean)                                                                    
                seen_in_this_page.add(pattern)                                                                   
                                                                                                                 
            for pattern in seen_in_this_page:                                                                    
                pattern_page_counts[pattern] += 1                                                                
                                                                                                                 
        # Identify recurring patterns                                                                            
        repeated_patterns = {                                                                                    
            pattern                                                                                              
            for pattern, count in pattern_page_counts.items()                                                    
            if count >= threshold                                                                                
        }                                                                                                        
                                                                                                                 
        # Filter out repeated lines from each page                                                               
        cleaned_pages: list[str] = []                                                                            
        for page_text in pages:                                                                                  
            retained_lines: list[str] = []                                                                       
            for line in page_text.splitlines():                                                                  
                pattern = line_pattern(line)                                                                     
                if pattern in repeated_patterns:                                                                 
                    continue                                                                                     
                retained_lines.append(line)                                                                      
            cleaned_pages.append("\n".join(retained_lines))                                                      
                                                                                                                 
        return cleaned_pages