from typing import Protocol, Sequence, runtime_checkable                                                                   
import numpy as np                                                                                                         
                                                                                                                            
                                                                                                                            
def l2_normalize(vectors: np.ndarray, eps: float = 1e-12) -> np.ndarray:                                                   
    """L2-normalize 1D or 2D vectors to unit length.                                                                       
                                                                                                                            
    Safe against zero vectors: returns zero vectors without producing NaN.                                                 
    Always returns a float32 ndarray.                                                                                      
    """                                                                                                                    
    arr = np.asarray(vectors, dtype=np.float32)                                                                            
                                                                                                                            
    if arr.ndim == 1:                                                                                                      
        norm = float(np.linalg.norm(arr))                                                                                  
        if norm < eps:                                                                                                     
            return np.zeros_like(arr, dtype=np.float32)                                                                    
        return (arr / norm).astype(np.float32)                                                                             
                                                                                                                            
    if arr.ndim == 2:                                                                                                      
        norms = np.linalg.norm(arr, axis=1, keepdims=True)                                                                 
        zero_mask = norms < eps                                                                                            
        safe_norms = np.where(zero_mask, 1.0, norms)                                                                       
        normalized = arr / safe_norms                                                                                      
        normalized[zero_mask.squeeze(axis=-1)] = 0.0                                                                       
        return normalized.astype(np.float32)                                                                               
                                                                                                                            
    raise ValueError(f"Expected 1D or 2D array, got shape {arr.shape}")                                                    
                                                                                                                            
                                                                                                                            
@runtime_checkable                                                                                                         
class Embedder(Protocol):                                                                                                  
    """Protocol for embedding providers."""                                                                                
                                                                                                                            
    model_id: str                                                                                                          
    dimensions: int                                                                                                        
    max_input_tokens: int                                                                                                  
                                                                                                                            
    def embed_documents(self, texts: Sequence[str]) -> np.ndarray:                                                         
        """Embed a sequence of document texts into a 2D float32 array (n, dimensions)."""                                  
        ...                                                                                                                
                                                                                                                            
    def embed_query(self, text: str) -> np.ndarray:                                                                        
        """Embed a single query string into a 1D float32 array (dimensions,)."""                                           
        ...