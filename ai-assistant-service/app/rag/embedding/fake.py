"""Deterministic fake embedder using feature hashing for offline testing."""

import hashlib
import re
from typing import Sequence
import numpy as np

from app.rag.embedding.base import Embedder, l2_normalize


class FakeEmbedder(Embedder):
    """A deterministic, dependency-free embedder for tests implementing the Embedder interface.

    Uses feature hashing (bag-of-words) to project text into a fixed-dimensional space.
    Texts with common words will have higher cosine similarity.
    Tracks call counts and seen texts to help verify caching and batching behaviors.
    """

    def __init__(
        self,
        dimensions: int = 256,
        model_id: str = "fake/deterministic-bow",
        max_input_tokens: int = 512,
    ) -> None:
        self._dimensions = dimensions
        self._model_id = model_id
        self._max_input_tokens = max_input_tokens
        self.call_count: int = 0
        self.texts_seen: int = 0

    @property
    def model_id(self) -> str:
        return self._model_id

    @property
    def dimensions(self) -> int:
        return self._dimensions

    @property
    def max_input_tokens(self) -> int:
        return self._max_input_tokens

    def _text_to_vector(self, text: str) -> np.ndarray:
        tokens = re.findall(r"\w+", text.lower())
        vec = np.zeros(self._dimensions, dtype=np.float32)

        if not tokens:
            return vec

        for token in tokens:
            # Deterministic hash to an index in [0, dimensions)
            h = int(hashlib.md5(token.encode("utf-8")).hexdigest(), 16)
            idx = h % self._dimensions
            vec[idx] += 1.0

        return l2_normalize(vec)

    def count_tokens(self, text: str) -> int:
        """Count tokens using regex word extraction."""
        return len(re.findall(r"\w+", text))

    def embed_documents(self, texts: Sequence[str]) -> np.ndarray:
        """Embed a sequence of texts into a 2D float32 array (n, dimensions)."""
        if not texts:
            return np.empty((0, self._dimensions), dtype=np.float32)

        for idx, t in enumerate(texts):
            c_tokens = self.count_tokens(t)
            if c_tokens > self._max_input_tokens:
                raise ValueError(
                    f"Text at index {idx} has {c_tokens} tokens, exceeding max_input_tokens={self._max_input_tokens}. "
                    f"Embedders must not truncate silently."
                )

        self.call_count += 1
        self.texts_seen += len(texts)

        vectors = [self._text_to_vector(t) for t in texts]
        return np.vstack(vectors).astype(np.float32)

    def embed_query(self, text: str) -> np.ndarray:
        """Embed a single query text into a 1D float32 array (dimensions,)."""
        c_tokens = self.count_tokens(text)
        if c_tokens > self._max_input_tokens:
            raise ValueError(
                f"Query has {c_tokens} tokens, exceeding max_input_tokens={self._max_input_tokens}. "
                f"Embedders must not truncate silently."
            )

        self.call_count += 1
        self.texts_seen += 1
        return self._text_to_vector(text)

