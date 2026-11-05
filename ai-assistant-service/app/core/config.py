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
