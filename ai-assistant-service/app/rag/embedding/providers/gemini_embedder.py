"""Gemini embedding provider implementation using google-genai SDK."""

from typing import Any, Sequence
import numpy as np
from google import genai
from google.genai import types

from app.core.config import settings
from app.rag.embedding.base import Embedder, l2_normalize
from app.rag.embedding.batching import batched, validate_non_empty_texts, with_retry
from app.rag.embedding.models import EmbeddingConfig


class GeminiEmbedder(Embedder):
    """Embedder implementation for Google Gemini embedding models."""

    def __init__(
        self,
        config: EmbeddingConfig,
        api_key: str | None = None,
        client: Any = None,
    ) -> None:
        self.config = config
        self._model_id = config.model_id()
        self._dimensions = config.dimensions or 768
        self._max_input_tokens = 2048

        if client is not None:
            self.client = client
        else:
            resolved_key = api_key or settings.GEMINI_API_KEY
            self.client = genai.Client(api_key=resolved_key)

    @property
    def model_id(self) -> str:
        return self._model_id

    @property
    def dimensions(self) -> int:
        return self._dimensions

    @property
    def max_input_tokens(self) -> int:
        return self._max_input_tokens

    def embed_documents(self, texts: Sequence[str]) -> np.ndarray:
        """Embed a sequence of documents using RETRIEVAL_DOCUMENT task type."""
        if not texts:
            return np.empty((0, self._dimensions), dtype=np.float32)

        validate_non_empty_texts(texts)

        all_vectors: list[list[float]] = []

        cfg_kwargs: dict[str, Any] = {"task_type": "RETRIEVAL_DOCUMENT"}
        if self.config.dimensions is not None:
            cfg_kwargs["output_dimensionality"] = self.config.dimensions
        embed_config = types.EmbedContentConfig(**cfg_kwargs)

        for batch in batched(texts, self.config.batch_size):
            response = with_retry(
                lambda: self.client.models.embed_content(
                    model=self.config.model,
                    contents=list(batch),
                    config=embed_config,
                )
            )
            for emb in response.embeddings:
                all_vectors.append(emb.values)

        matrix = np.array(all_vectors, dtype=np.float32)
        if self.config.normalize:
            return l2_normalize(matrix)
        return matrix

    def embed_query(self, text: str) -> np.ndarray:
        """Embed a single query using RETRIEVAL_QUERY task type."""
        validate_non_empty_texts([text])

        cfg_kwargs: dict[str, Any] = {"task_type": "RETRIEVAL_QUERY"}
        if self.config.dimensions is not None:
            cfg_kwargs["output_dimensionality"] = self.config.dimensions
        embed_config = types.EmbedContentConfig(**cfg_kwargs)

        response = with_retry(
            lambda: self.client.models.embed_content(
                model=self.config.model,
                contents=text,
                config=embed_config,
            )
        )
        vec = np.array(response.embeddings[0].values, dtype=np.float32)
        if self.config.normalize:
            return l2_normalize(vec)
        return vec
