from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Service Info
    SERVICE_NAME: str = "ai-assistant-service"
    PORT: int = 8089
    ENVIRONMENT: str = "development"
    DEBUG: bool = True

    # API Keys
    OPENAI_API_KEY: str = ""
    ANTHROPIC_API_KEY: str = ""
    GEMINI_API_KEY: str = ""
    DEFAULT_LLM_PROVIDER: str = "gemini"

    LOCAL_LLM_BASE_URL: str = ""
    LOCAL_LLM_MODEL: str = ""

    # Embedding Configuration
    EMBEDDING_PROVIDER: str = "openai"
    EMBEDDING_MODEL: str = "text-embedding-3-small"
    EMBEDDING_DIMENSIONS: int | None = None

    # Qdrant Vector Store Configuration
    QDRANT_URL: str = "http://localhost:6333"
    QDRANT_API_KEY: str = ""
    QDRANT_COLLECTION_PREFIX: str = "commerce_docs"

    # RAG Generation Configuration
    RAG_LLM_PROVIDER: str = ""  # Boşsa DEFAULT_LLM_PROVIDER kullanılır
    RAG_LLM_MODEL: str = ""     # Boşsa seçilen sağlayıcının varsayılan modeli kullanılır
    RAG_TEMPERATURE: float = 0.0
    RAG_MAX_OUTPUT_TOKENS: int = 400
    RAG_LLM_TIMEOUT_SEC: float = 30.0
    RAG_CONTEXT_TOKEN_BUDGET: int = 1500
    RAG_TOP_K: int = 5
    RAG_MIN_DENSE_SCORE: float | None = None
    RAG_MAX_ATTEMPTS: int = 2
    RAG_ABSTAIN_MESSAGE: str = (
        "Bu konuda dokümanlarımızda bilgi bulamadım. Sizi bir müşteri temsilcisine yönlendirebilirim."
    )
    RAG_RETRIEVAL_MODE: str = "hybrid"  # 'dense', 'sparse', 'hybrid'

    # Pydantic Settings
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",  # .env içinde bilmediği bir değişken varsa hata fırlatma, görmezden gel
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
