"""SQLite-backed disk embedding cache and cached embedder wrapper."""

import hashlib
import sqlite3
from pathlib import Path
from typing import Sequence
import numpy as np

from app.rag.embedding.base import Embedder
from app.rag.embedding.models import EmbedKind


class DiskEmbeddingCache:
    """Persistent disk cache for embedding vectors using SQLite.

    Stores vectors as raw float32 binary blobs.
    Safe against corrupted/missing database files by recreating the schema on connect.
    """

    def __init__(self, db_path: Path | str) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)

    def _init_db(self) -> None:
        try:
            with self._get_connection() as conn:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS embeddings (
                        key TEXT PRIMARY KEY,
                        vector BLOB NOT NULL
                    )
                    """
                )
                conn.commit()
        except Exception:
            pass

    @staticmethod
    def build_key(model_id: str, dimensions: int, kind: EmbedKind, text: str) -> str:
        """Create a deterministic cache key based on model spec, kind, and text."""
        norm_text = text.strip()
        raw = f"{model_id}|{dimensions}|{kind.value}|{norm_text}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def get(self, key: str, dimensions: int) -> np.ndarray | None:
        """Retrieve a cached vector by key, or None if missing."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT vector FROM embeddings WHERE key = ?", (key,))
                row = cursor.fetchone()
                if row is None:
                    return None
                blob = row[0]
                vec = np.frombuffer(blob, dtype=np.float32)
                if vec.shape != (dimensions,):
                    return None
                return vec.copy()
        except Exception:
            return None

    def set(self, key: str, vector: np.ndarray) -> None:
        """Store a vector under the given key."""
        try:
            blob = vector.astype(np.float32).tobytes()
            with self._get_connection() as conn:
                conn.execute(
                    "INSERT OR REPLACE INTO embeddings (key, vector) VALUES (?, ?)",
                    (key, blob),
                )
                conn.commit()
        except Exception:
            pass

    def get_many(self, keys: Sequence[str], dimensions: int) -> dict[str, np.ndarray]:
        """Retrieve multiple vectors at once."""
        if not keys:
            return {}
        results: dict[str, np.ndarray] = {}
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                placeholders = ",".join("?" for _ in keys)
                cursor.execute(
                    f"SELECT key, vector FROM embeddings WHERE key IN ({placeholders})",
                    list(keys),
                )
                for k, blob in cursor.fetchall():
                    vec = np.frombuffer(blob, dtype=np.float32)
                    if vec.shape == (dimensions,):
                        results[k] = vec.copy()
        except Exception:
            pass
        return results

    def set_many(self, items: list[tuple[str, np.ndarray]]) -> None:
        """Store multiple vectors in a single transaction."""
        if not items:
            return
        try:
            data = [(k, vec.astype(np.float32).tobytes()) for k, vec in items]
            with self._get_connection() as conn:
                conn.executemany(
                    "INSERT OR REPLACE INTO embeddings (key, vector) VALUES (?, ?)",
                    data,
                )
                conn.commit()
        except Exception:
            pass


class CachedEmbedder(Embedder):
    """Transparent caching wrapper implementing the Embedder interface.

    Maintains call stats (hits, misses) and batches uncached documents to inner embedder.
    """

    def __init__(self, inner: Embedder, cache: DiskEmbeddingCache) -> None:
        self.inner = inner
        self.cache = cache
        self.hits: int = 0
        self.misses: int = 0

    @property
    def model_id(self) -> str:
        return self.inner.model_id

    @property
    def dimensions(self) -> int:
        return self.inner.dimensions

    @property
    def max_input_tokens(self) -> int:
        return self.inner.max_input_tokens

    def embed_query(self, text: str) -> np.ndarray:
        key = self.cache.build_key(
            self.model_id, self.dimensions, EmbedKind.QUERY, text
        )
        cached = self.cache.get(key, self.dimensions)
        if cached is not None:
            self.hits += 1
            return cached

        self.misses += 1
        vec = self.inner.embed_query(text)
        self.cache.set(key, vec)
        return vec

    def embed_documents(self, texts: Sequence[str]) -> np.ndarray:
        if not texts:
            return np.empty((0, self.dimensions), dtype=np.float32)

        keys = [
            self.cache.build_key(self.model_id, self.dimensions, EmbedKind.DOCUMENT, t)
            for t in texts
        ]
        cached_dict = self.cache.get_many(keys, self.dimensions)

        missing_indices: list[int] = []
        missing_texts: list[str] = []

        for idx, (t, k) in enumerate(zip(texts, keys)):
            if k not in cached_dict:
                missing_indices.append(idx)
                missing_texts.append(t)

        self.hits += len(texts) - len(missing_indices)
        self.misses += len(missing_indices)

        # Call inner embedder only for missing texts
        if missing_texts:
            new_vectors = self.inner.embed_documents(missing_texts)
            to_cache = []
            for idx, vec in zip(missing_indices, new_vectors):
                k = keys[idx]
                cached_dict[k] = vec
                to_cache.append((k, vec))
            self.cache.set_many(to_cache)

        # Reconstruct output preserving original order
        ordered = [cached_dict[k] for k in keys]
        return np.vstack(ordered).astype(np.float32)
