from enum import StrEnum                                                                                                   
from pydantic import BaseModel, ConfigDict, Field, field_validator    

class EmbedKind(StrEnum):                                                                                                  
    """Indicates whether an embedding is for a search query or a document chunk."""                                        
                                                                                                                            
    QUERY = "query"                                                                                                        
    DOCUMENT = "document"

class EmbeddingConfig(BaseModel):                                                                                          
    """Configuration for an embedder instance."""                                                                          
                                                                                                                            
    model_config = ConfigDict(frozen=True)                                                                                 
                                                                                                                            
    provider: str                                                                                                          
    model: str                                                                                                             
    dimensions: int | None = None                                                                                          
    batch_size: int = Field(default=64, ge=1)                                                                              
    normalize: bool = True                                                                                                 
                                                                                                                            
    @field_validator("dimensions")                                                                                         
    @classmethod                                                                                                           
    def validate_dimensions(cls, v: int | None) -> int | None:                                                             
        if v is not None and v <= 0:                                                                                       
            raise ValueError("dimensions must be greater than 0 if specified")                                             
        return v                                                                                                           
                                                                                                                            
    def model_id(self) -> str:                                                                                             
        """Unique identifier formatted as provider/model[@dimensions] for caching/reporting."""                            
        if self.dimensions is not None:                                                                                    
            return f"{self.provider}/{self.model}@{self.dimensions}"                                                       
        return f"{self.provider}/{self.model}"