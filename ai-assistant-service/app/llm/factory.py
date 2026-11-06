import logging                                                                                                                 
from app.core.config import settings        
from enum import Enum                                                                                   
from app.llm.base import BaseLLMProvider                                                                                       
from app.llm.providers import (                                                                                                
    ClaudeProvider,                                                                                                            
    GeminiProvider,                                                                                                            
    LocalProvider,                                                                                                             
    OpenAIProvider,                                                                                                            
)     

logger = logging.getLogger(__name__) 


class LLMProviderType(str, Enum):                                                                                              
    GEMINI = "gemini"                                                                                                          
    LOCAL = "local"                                                                                                            
    OPENAI = "openai"                                                                                                          
    CLAUDE = "claude"

class LLMFactory:
    """                                                                                                                        
        Factory class responsible for dynamically instantiating the requested LLM provider.                                        
        Fallback to DEFAULT_LLM_PROVIDER from settings if no provider is explicitly specified.                                     
    """    

    @staticmethod
    def get_provider(
        provider_name: str | None = None,
        model_name: str | None = None,
    ) -> BaseLLMProvider:
        """                                                                                                                    
        Resolve and return the appropriate BaseLLMProvider instance.                                                           
                                                                                                                               
        Supported providers:                                                                                                   
            - 'gemini'                                                                                                           
            - 'local' (or 'ollama')                                                                                              
            - 'openai'                                                                                                           
            - 'claude' (or 'anthropic')                                                                                          
        """  
        raw_provider = (provider_name or settings.DEFAULT_LLM_PROVIDER).strip().lower()

        # Support aliases
        if raw_provider == "anthropic":
            selected_provider = LLMProviderType.CLAUDE
        elif raw_provider == "ollama":
            selected_provider = LLMProviderType.LOCAL
        else:
            selected_provider = raw_provider

        kwargs: dict[str, str] = {}
        if model_name:
            kwargs["model_name"] = model_name

        if selected_provider == LLMProviderType.GEMINI:
            return GeminiProvider(**kwargs)
        elif selected_provider == LLMProviderType.OPENAI:
            return OpenAIProvider(**kwargs)
        elif selected_provider == LLMProviderType.CLAUDE:
            return ClaudeProvider(**kwargs)
        elif selected_provider == LLMProviderType.LOCAL:
            return LocalProvider(**kwargs)
        else:
            raise ValueError(f"Unsupported LLM provider: '{raw_provider}'")

