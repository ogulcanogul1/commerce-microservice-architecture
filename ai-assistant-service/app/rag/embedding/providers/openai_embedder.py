"""OpenAI embedding provider implementation."""

from typing import Any, Sequence
import numpy as np
import openai

from app.core.config import settings
from app.rag.embedding.base import Embedder, l2_normalize
from app.rag.embedding.batching import batched, validate_non_empty_texts, with_retry
from app.rag.embedding.models import EmbeddingConfig


class OpenAIEmbedder(Embedder):
    """Embedder implementation for OpenAI text-embedding models."""

    def __init__(
        self,
        config: EmbeddingConfig,
        api_key: str | None = None,
        client: Any = None,
    ) -> None:
        self.config = config
        self._model_id = config.model_id()
        self._dimensions = config.dimensions or (
            3072 if "large" in config.model else 1536
        )
        self._max_input_tokens = 8191
        import tiktoken
        self._tokenizer = tiktoken.get_encoding("cl100k_base")

        if client is not None:
            self.client = client
        else:
            resolved_key = api_key or settings.OPENAI_API_KEY
            self.client = openai.OpenAI(api_key=resolved_key)

    @property
    def model_id(self) -> str:
        return self._model_id

    @property
    def dimensions(self) -> int:
        return self._dimensions

    @property
    def max_input_tokens(self) -> int:
        return self._max_input_tokens

    def count_tokens(self, text: str) -> int:
        """Count tokens using tiktoken cl100k_base tokenizer."""
        return len(self._tokenizer.encode(text, disallowed_special=()))

    def embed_documents(self, texts: Sequence[str]) -> np.ndarray:
        """Embed a sequence of texts using OpenAI's embeddings API in batches."""
        if not texts:
            return np.empty((0, self._dimensions), dtype=np.float32)

        validate_non_empty_texts(texts)

        for idx, t in enumerate(texts):
            c_tokens = self.count_tokens(t)
            if c_tokens > self._max_input_tokens:
                raise ValueError(
                    f"Text at index {idx} has {c_tokens} tokens, exceeding max_input_tokens={self._max_input_tokens}. "
                    f"Embedders must not truncate silently."
                )

        all_vectors: list[list[float]] = []

        for batch in batched(texts, self.config.batch_size):
            kwargs: dict[str, Any] = {
                "model": self.config.model,
                "input": list(batch),
            }
            if self.config.dimensions is not None:
                kwargs["dimensions"] = self.config.dimensions

            response = with_retry(lambda: self.client.embeddings.create(**kwargs))
            for item in response.data:
                all_vectors.append(item.embedding)

        matrix = np.array(all_vectors, dtype=np.float32)
        if self.config.normalize:
            return l2_normalize(matrix)
        return matrix

    def embed_query(self, text: str) -> np.ndarray:
        """Embed a search query text."""
        validate_non_empty_texts([text])
        docs = self.embed_documents([text])
        return docs[0]
