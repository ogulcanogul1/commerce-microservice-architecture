import numpy as np                                                                                                         
import pytest                                                                                                              
from pydantic import ValidationError                                                                                       
                                                                                                                            
from app.rag.embedding.base import Embedder, l2_normalize                                                                  
from app.rag.embedding.models import EmbedKind, EmbeddingConfig                                                            
                                                                                                                            
                                                                                                                            
def test_embed_kind_values():                                                                                              
    assert EmbedKind.QUERY == "query"                                                                                      
    assert EmbedKind.DOCUMENT == "document"                                                                                
                                                                                                                            
                                                                                                                            
def test_embedding_config_defaults_and_model_id():                                                                         
    cfg = EmbeddingConfig(provider="openai", model="text-embedding-3-small")                                               
    assert cfg.batch_size == 64                                                                                            
    assert cfg.normalize is True                                                                                           
    assert cfg.dimensions is None                                                                                          
    assert cfg.model_id() == "openai/text-embedding-3-small"                                                               
                                                                                                                            
    cfg_dim = EmbeddingConfig(provider="openai", model="text-embedding-3-small", dimensions=512)                           
    assert cfg_dim.model_id() == "openai/text-embedding-3-small@512"                                                       
                                                                                                                            
                                                                                                                            
def test_embedding_config_immutability():                                                                                  
    cfg = EmbeddingConfig(provider="openai", model="text-embedding-3-small")                                               
    with pytest.raises(ValidationError):                                                                                   
        cfg.batch_size = 32  # frozen=True                                                                                 
                                                                                                                            
                                                                                                                            
def test_embedding_config_validations():                                                                                   
    with pytest.raises(ValidationError):                                                                                   
        EmbeddingConfig(provider="test", model="m", batch_size=0)                                                          
                                                                                                                            
    with pytest.raises(ValidationError):                                                                                   
        EmbeddingConfig(provider="test", model="m", dimensions=-1)                                                         
                                                                                                                            
    with pytest.raises(ValidationError):                                                                                   
        EmbeddingConfig(provider="test", model="m", dimensions=0)                                                          
                                                                                                                            
                                                                                                                            
def test_l2_normalize_1d():                                                                                                
    vec = np.array([3.0, 4.0], dtype=np.float32)                                                                           
    normalized = l2_normalize(vec)                                                                                         
    assert normalized.dtype == np.float32                                                                                  
    assert np.isclose(np.linalg.norm(normalized), 1.0)                                                                     
    assert np.allclose(normalized, np.array([0.6, 0.8], dtype=np.float32))                                                 
                                                                                                                            
                                                                                                                            
def test_l2_normalize_2d():                                                                                                
    mat = np.array([[3.0, 4.0], [1.0, 1.0]], dtype=np.float32)                                                             
    normalized = l2_normalize(mat)                                                                                         
    assert normalized.dtype == np.float32                                                                                  
    norms = np.linalg.norm(normalized, axis=1)                                                                             
    assert np.allclose(norms, [1.0, 1.0])                                                                                  
                                                                                                                            
                                                                                                                            
def test_l2_normalize_zero_vector_safety():                                                                                
    # 1D sıfır vektör                                                                                                      
    zero_1d = np.zeros(5, dtype=np.float32)                                                                                
    norm_1d = l2_normalize(zero_1d)                                                                                        
    assert not np.isnan(norm_1d).any()                                                                                     
    assert np.all(norm_1d == 0.0)                                                                                          
                                                                                                                            
    # 2D içinde sıfır vektör olan matris                                                                                   
    mixed_2d = np.array([[0.0, 0.0], [0.0, 3.0]], dtype=np.float32)                                                        
    norm_2d = l2_normalize(mixed_2d)                                                                                       
    assert not np.isnan(norm_2d).any()                                                                                     
    assert np.all(norm_2d[0] == 0.0)                                                                                       
    assert np.isclose(np.linalg.norm(norm_2d[1]), 1.0)                                                                     
                                                                                                                            
                                                                                                                            
def test_embedder_protocol_runtime_checkable():                                                                            
    class ValidEmbedder:                                                                                                   
        model_id = "test/model"                                                                                            
        dimensions = 128                                                                                                   
        max_input_tokens = 512                                                                                             
                                                                                                                            
        def embed_documents(self, texts):                                                                                  
            return np.zeros((len(texts), 128), dtype=np.float32)                                                           
                                                                                                                            
        def embed_query(self, text):                                                                                       
            return np.zeros(128, dtype=np.float32)                                                                         
                                                                                                                            
    class IncompleteEmbedder:                                                                                              
        model_id = "test/model"                                                                                            
                                                                                                                            
    assert isinstance(ValidEmbedder(), Embedder)                                                                           
    assert not isinstance(IncompleteEmbedder(), Embedder)