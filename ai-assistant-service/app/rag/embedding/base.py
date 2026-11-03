"""Base interface and normalization utilities for embedding."""

from abc import ABC, abstractmethod
from typing import Sequence
import numpy as np


def l2_normalize(vectors: np.ndarray, eps: float = 1e-12) -> np.ndarray:
    """L2-normalize 1D or 2D vectors to unit length.

    Safe against zero vectors: returns zero vectors without producing NaN.
    Always returns a float32 ndarray.
    """
    arr = np.asarray(vectors, dtype=np.float32)

    if arr.ndim == 1:
        norm = float(np.linalg.norm(arr))
        if norm < eps:
            return np.zeros_like(arr, dtype=np.float32)
        return (arr / norm).astype(np.float32)

    if arr.ndim == 2:
        norms = np.linalg.norm(arr, axis=1, keepdims=True)
        zero_mask = norms < eps
        safe_norms = np.where(zero_mask, 1.0, norms)
        normalized = arr / safe_norms
        normalized[zero_mask.squeeze(axis=-1)] = 0.0
        return normalized.astype(np.float32)

    raise ValueError(f"Expected 1D or 2D array, got shape {arr.shape}")


class Embedder(ABC):
    """Abstract Base Class (Interface) for all embedding providers."""

    @property
    @abstractmethod
    def model_id(self) -> str:
        """Unique identifier formatted as provider/model[@dimensions]."""
        ...

    @property
    @abstractmethod
    def dimensions(self) -> int:
        """Embedding vector dimension."""
        ...

    @property
    @abstractmethod
    def max_input_tokens(self) -> int:
        """Maximum context window allowed for a single input text."""
        ...

    @abstractmethod
    def embed_documents(self, texts: Sequence[str]) -> np.ndarray:
        """Embed a sequence of document texts into a 2D float32 array (n, dimensions)."""
        ...

    @abstractmethod
    def embed_query(self, text: str) -> np.ndarray:
        """Embed a single query string into a 1D float32 array (dimensions,)."""
        ...
