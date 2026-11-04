"""Local embedding provider supporting both sentence-transformers and OpenAI-compatible endpoints."""

from typing import Any, Sequence
import numpy as np
import openai

from app.core.config import settings
from app.rag.embedding.base import Embedder, l2_normalize
from app.rag.embedding.batching import batched, validate_non_empty_texts, with_retry
from app.rag.embedding.models import EmbeddingConfig


class LocalEmbedder(Embedder):
    """Embedder for local execution.

    Supports:
    1. Remote local endpoint (OpenAI-compatible server like Ollama, vLLM, llama.cpp) via base_url.
    2. In-process sentence-transformers model (requires optional sentence-transformers package).

    Handles prefix rules:
    - Multilingual-E5 models require 'query: ' for queries and 'passage: ' for documents.
    - BGE-M3 models do not require prefixes.
    """

    def __init__(
        self,
        config: EmbeddingConfig,
        base_url: str | None = None,
        client: Any = None,
    ) -> None:
        self.config = config
        self._model_id = config.model_id()
        self.is_e5 = "e5" in config.model.lower()

        # Dimension defaults based on model family
        if config.dimensions is not None:
            self._dimensions = config.dimensions
        elif "bge-m3" in config.model.lower():
            self._dimensions = 1024
        elif "small" in config.model.lower():
            self._dimensions = 384
        else:
            self._dimensions = 768

        # Max input tokens
        if "bge-m3" in config.model.lower():
            self._max_input_tokens = 8192
        elif self.is_e5:
            self._max_input_tokens = 512
        else:
            self._max_input_tokens = 2048

        self.base_url = base_url or settings.LOCAL_LLM_BASE_URL
        self._st_model: Any = None
        self.client: Any = None

        if client is not None:
            self.client = client
        elif self.base_url:
            self.client = openai.OpenAI(
                base_url=self.base_url,
                api_key="local-dummy-key",
            )
        else:
            # In-process sentence-transformers mode (lazy loaded)
            pass

    @property
    def model_id(self) -> str:
        return self._model_id

    @property
    def dimensions(self) -> int:
        return self._dimensions

    @property
    def max_input_tokens(self) -> int:
        return self._max_input_tokens

    def _get_st_model(self) -> Any:
        if self._st_model is None:
            try:
                from sentence_transformers import SentenceTransformer

                self._st_model = SentenceTransformer(self.config.model)
            except ImportError as err:
                raise ImportError(
                    "sentence-transformers is not installed. Either run "
                    "'uv add sentence-transformers' or set LOCAL_LLM_BASE_URL "
                    "to use an OpenAI-compatible local server."
                ) from err
        return self._st_model

    def _apply_doc_prefix(self, text: str) -> str:
        if self.is_e5 and not text.startswith("passage: "):
            return f"passage: {text}"
        return text

    def _apply_query_prefix(self, text: str) -> str:
        if self.is_e5 and not text.startswith("query: "):
            return f"query: {text}"
        return text

    def embed_documents(self, texts: Sequence[str]) -> np.ndarray:
        if not texts:
            return np.empty((0, self._dimensions), dtype=np.float32)

        validate_non_empty_texts(texts)
        prefixed_texts = [self._apply_doc_prefix(t) for t in texts]

        all_vectors: list[list[float]] = []

        if self.client is not None:
            for batch in batched(prefixed_texts, self.config.batch_size):
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
        else:
            st_model = self._get_st_model()
            matrix = st_model.encode(
                prefixed_texts,
                batch_size=self.config.batch_size,
                convert_to_numpy=True,
                show_progress_bar=False,
            ).astype(np.float32)

        if self.config.normalize:
            return l2_normalize(matrix)
        return matrix

    def embed_query(self, text: str) -> np.ndarray:
        validate_non_empty_texts([text])
        prefixed_query = self._apply_query_prefix(text)

        if self.client is not None:
            kwargs: dict[str, Any] = {
                "model": self.config.model,
                "input": [prefixed_query],
            }
            if self.config.dimensions is not None:
                kwargs["dimensions"] = self.config.dimensions
            response = with_retry(lambda: self.client.embeddings.create(**kwargs))
            vec = np.array(response.data[0].embedding, dtype=np.float32)
            if self.config.normalize:
                return l2_normalize(vec)
            return vec

        st_model = self._get_st_model()
        vec = st_model.encode(
            prefixed_query,
            convert_to_numpy=True,
            show_progress_bar=False,
        ).astype(np.float32)

        if self.config.normalize:
            return l2_normalize(vec)
        return vec
