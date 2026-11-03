import re                                                                                                                  
from typing import Protocol, runtime_checkable                                                                             
import tiktoken 

@runtime_checkable                                                                                                         
class Tokenizer(Protocol):                                                                                                 
    """Protocol defining the tokenizer interface required for chunking."""                                                 
                                                                                                                            
    def count(self, text: str) -> int:                                                                                     
        """Return the number of tokens in text."""                                                                         
        ...                                                                                                                
                                                                                                                            
    def token_spans(self, text: str) -> list[tuple[int, int]]:                                                             
        """Return the (char_start, char_end) offsets for each token in text."""                                            
        ...   

class WhitespaceTokenizer:                                                                                                 
    """Simple whitespace-based tokenizer (uses \\S+ regex).                                                                
                                                                                                                            
    Predictable, fast, and dependency-free. Ideal for unit tests.                                                          
    """                                                                                                                    
                                                                                                                            
    _TOKEN_RE = re.compile(r"\S+")                                                                                         
                                                                                                                            
    def count(self, text: str) -> int:                                                                                     
        if not text:                                                                                                       
            return 0                                                                                                       
        return len(self._TOKEN_RE.findall(text))                                                                           
                                                                                                                            
    def token_spans(self, text: str) -> list[tuple[int, int]]:                                                             
        if not text:                                                                                                       
            return []                                                                                                      
        return [match.span() for match in self._TOKEN_RE.finditer(text)]                                                   
                                                                                                                               
                                                                                                                               
class TiktokenTokenizer:                                                                                                   
    """Byte-pair encoding tokenizer using tiktoken (default: cl100k_base).                                                 
                                                                                                                            
    Handles UTF-8 multi-byte characters correctly by aligning spans                                                        
    to Unicode character boundaries rather than raw byte offsets.                                                          
    """                                                                                                                    
                                                                                                                            
    def __init__(self, encoding_name: str = "cl100k_base") -> None:                                                        
        self.encoding_name = encoding_name                                                                                 
        self.encoding = tiktoken.get_encoding(encoding_name)                                                               
                                                                                                                            
    def count(self, text: str) -> int:                                                                                     
        if not text:                                                                                                       
            return 0                                                                                                       
        return len(self.encoding.encode(text, disallowed_special=()))                                                      
                                                                                                                            
    def token_spans(self, text: str) -> list[tuple[int, int]]:                                                             
        if not text:                                                                                                       
            return []                                                                                                      
                                                                                                                            
        token_ids = self.encoding.encode(text, disallowed_special=())                                                      
        if not token_ids:                                                                                                  
            return []                                                                                                      
                                                                                                                            
        token_bytes_list = self.encoding.decode_tokens_bytes(token_ids)                                                    
        spans: list[tuple[int, int]] = []                                                                                  
        char_cursor = 0                                                                                                    
        byte_buffer = b""                                                                                                  
                                                                                                                            
        for t_bytes in token_bytes_list:                                                                                   
            byte_buffer += t_bytes                                                                                         
            try:                                                                                                           
                # Decode to string to calculate valid Unicode character length                                             
                decoded_str = byte_buffer.decode("utf-8")                                                                  
                char_length = len(decoded_str)                                                                             
                span_start = char_cursor                                                                                   
                span_end = char_cursor + char_length                                                                       
                spans.append((span_start, span_end))                                                                       
                char_cursor = span_end                                                                                     
                byte_buffer = b""                                                                                          
            except UnicodeDecodeError:                                                                                     
                # Multi-byte UTF-8 character split across token boundary;                                                  
                # accumulate into buffer until complete.                                                                   
                continue                                                                                                   
                                                                                                                            
        if byte_buffer:                                                                                                    
            decoded_str = byte_buffer.decode("utf-8", errors="replace")                                                    
            spans.append((char_cursor, char_cursor + len(decoded_str)))                                                    
                                                                                                                            
        return spans