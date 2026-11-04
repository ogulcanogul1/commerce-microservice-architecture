"""Domain models and configuration for embedding operations."""

from enum import StrEnum
from pydantic import BaseModel, ConfigDict, Field, field_validator


class EmbedKind(StrEnum):
    """Indicates whether an embedding is for a search query or a document chunk."""

    QUERY = "query"
    DOCUMENT = "document"


class EmbeddingProvider(StrEnum):
    """Supported embedding model providers."""

    OPENAI = "openai"
    GEMINI = "gemini"
    LOCAL = "local"
    FAKE = "fake"


class EmbeddingConfig(BaseModel):
    """Configuration for an embedder instance."""

    model_config = ConfigDict(frozen=True)

    provider: EmbeddingProvider | str = EmbeddingProvider.OPENAI
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
        prov_val = self.provider.value if isinstance(self.provider, EmbeddingProvider) else str(self.provider)
        if self.dimensions is not None:
            return f"{prov_val}/{self.model}@{self.dimensions}"
        return f"{prov_val}/{self.model}"
