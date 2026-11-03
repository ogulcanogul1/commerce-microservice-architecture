import hashlib
import json                                                                                                                
from typing import Literal                                                                                                 
from pydantic import BaseModel, Field, field_validator, model_validator                                                    
                                                                                                                        
from app.rag.ingestion.models import ElementType 


class ChunkingConfig(BaseModel):                                                                                           
    """Configuration for document chunking strategies."""                                                                  
    max_tokens: int = Field(default=300, gt=0, description="Maximum token capacity per chunk")                             
    overlap_tokens: int = Field(default=45, ge=0, description="Token overlap between consecutive chunks")                  
    min_tokens: int = Field(default=60, ge=0, description="Minimum tokens threshold for merging small sections")           
    include_breadcrumb: bool = Field(default=True, description="Whether to include heading hierarchy as context prefix")   
    isolate_tables: bool = Field(default=False, description="Whether tables should strictly be kept in isolated chunks")   
                                                                                                                            
    model_config = {                                                                                                       
        "frozen": True,                                                                                                    
        "extra": "forbid",                                                                                                 
    }                                                                                                                      
                                                                                                                            
    @model_validator(mode="after")                                                                                         
    def validate_token_thresholds(self) -> "ChunkingConfig":                                                               
        if self.overlap_tokens >= self.max_tokens:                                                                         
            raise ValueError(                                                                                              
                f"overlap_tokens ({self.overlap_tokens}) must be strictly less than max_tokens ({self.max_tokens})."       
            )                                                                                                              
        if self.min_tokens > self.max_tokens:                                                                              
            raise ValueError(                                                                                              
                f"min_tokens ({self.min_tokens}) cannot be greater than max_tokens ({self.max_tokens})."                   
            )                                                                                                              
        return self                                                                                                        
                                                                                                                            
    def config_hash(self) -> str:                                                                                          
        """Deterministic short hash representing this specific configuration."""                                           
        payload = json.dumps(                                                                                              
            {                                                                                                              
                "max_tokens": self.max_tokens,                                                                             
                "overlap_tokens": self.overlap_tokens,                                                                     
                "min_tokens": self.min_tokens,                                                                             
                "include_breadcrumb": self.include_breadcrumb,                                                             
                "isolate_tables": self.isolate_tables,                                                                     
            },                                                                                                             
            sort_keys=True,                                                                                                
        )                                                                                                                  
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:8]                                                     
                                                                                                                            
                                                                                                                            
class Chunk(BaseModel):                                                                                                    
    """Unified chunk model produced by all chunker implementations."""                                                     
    id: str = Field(description="Deterministic unique identifier for the chunk")                                           
    strategy: Literal["fixed", "recursive", "structure"] = Field(description="Chunking algorithm used")                    
    source_file: str = Field(description="Name or path of the source document")                                            
    chunk_index: int = Field(ge=0, description="0-based sequence index within the document")                               
                                                                                                                            
    text: str = Field(description="Raw text content of the chunk presented to the user/LLM")                               
    context_prefix: str = Field(default="", description="Hierarchical breadcrumb prefix (e.g. 'Section > Subsection')")    
    token_count: int = Field(ge=0, description="Count of tokens in this chunk's raw text")                                 
                                                                                                                            
    page_start: int = Field(ge=1, description="1-based starting page number")                                              
    page_end: int = Field(ge=1, description="1-based ending page number")                                                  
    heading_path: list[str] = Field(default_factory=list, description="Active heading hierarchy at this chunk")            
    element_types: list[ElementType] = Field(                                                                              
        default_factory=list,                                                                                              
        description="Types of elements included in this chunk"                                                             
    )                                                                                                                      
                                                                                                                            
    char_start: int = Field(ge=0, description="Character start offset in flattened document")                              
    char_end: int = Field(ge=0, description="Character end offset in flattened document")                                  
                                                                                                                            
    @field_validator("text")                                                                                               
    @classmethod                                                                                                           
    def validate_text_not_empty(cls, v: str) -> str:                                                                       
        if not v.strip():                                                                                                  
            raise ValueError("Chunk text cannot be empty or whitespace only.")                                             
        return v                                                                                                           
                                                                                                                            
    @model_validator(mode="after")                                                                                         
    def validate_page_and_char_ranges(self) -> "Chunk":                                                                    
        if self.page_end < self.page_start:                                                                                
            raise ValueError(f"page_end ({self.page_end}) cannot be less than page_start ({self.page_start}).")            
        if self.char_end < self.char_start:                                                                                
            raise ValueError(f"char_end ({self.char_end}) cannot be less than char_start ({self.char_start}).")            
        return self                                                                                                        
                                                                                                                            
    @property                                                                                                              
    def embedding_text(self) -> str:                                                                                       
        """Text used for embedding or lexical retrieval, including context prefix if present."""                           
        if self.context_prefix.strip():                                                                                    
            return f"{self.context_prefix.strip()}\n\n{self.text}"                                                         
        return self.text