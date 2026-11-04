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

        # E5 model ailesi (örn. intfloat/multilingual-e5-small) sorgu ve dokümanlar için
        # zorunlu 'query: ' ve 'passage: ' önekleri bekler. Model adında 'e5' geçip geçmediğini denetliyoruz.
        self.is_e5 = "e5" in config.model.lower()

        # Vektör boyutu (dimension): Konfigürasyondan gelmediyse model tipine göre varsayılan atıyoruz.
        # - BGE-M3 modelleri: 1024 boyut
        # - E5-small modelleri: 384 boyut
        # - Diğer genel açık kaynak modeller: 768 boyut
        if config.dimensions is not None:
            self._dimensions = config.dimensions
        elif "bge-m3" in config.model.lower():
            self._dimensions = 1024
        elif "small" in config.model.lower():
            self._dimensions = 384
        else:
            self._dimensions = 768

        # Maksimum girdi token limiti:
        # BGE-M3 uzun metinleri (8192 token) desteklerken, E5-small en fazla 512 token alabilir.
        if "bge-m3" in config.model.lower():
            self._max_input_tokens = 8192
        elif self.is_e5:
            self._max_input_tokens = 512
        else:
            self._max_input_tokens = 2048

        # Yerel sunucu adresi (Ollama / vLLM / llama.cpp vb.)
        self.base_url = base_url or settings.LOCAL_LLM_BASE_URL

        # Ağır PyTorch/sentence-transformers modelini belleğe hemen yüklememek için
        # başlangıçta None bırakıyoruz (Lazy Loading - Tembel Yükleme).
        self._st_model: Any = None
        self._tokenizer: Any = None
        self._tokenizer_loaded: bool = False
        self._cl100k_fallback: Any = None
        self.client: Any = None

        if client is not None:
            # Testlerde dışarıdan mock client enjekte etmek için kullanılır.
            self.client = client
        elif self.base_url:
            # Eğer bir URL tanımlıysa (örn. http://localhost:11434/v1), OpenAI istemcisi
            # bu yerel adrese yönlendirilir (Ollama / vLLM OpenAI API formatını destekler).
            self.client = openai.OpenAI(
                base_url=self.base_url,
                api_key="local-dummy-key",
            )
        else:
            # base_url yoksa, model process içinde sentence-transformers ile çalıştırılacaktır.
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

    def _get_tokenizer(self) -> Any:
        if not self._tokenizer_loaded:
            self._tokenizer_loaded = True
            if self._st_model is not None:
                self._tokenizer = self._st_model.tokenizer
            else:
                try:
                    from transformers import AutoTokenizer

                    self._tokenizer = AutoTokenizer.from_pretrained(self.config.model)
                except Exception:
                    self._tokenizer = None
        return self._tokenizer

    def count_tokens(self, text: str) -> int:
        """Count tokens using cached sentence-transformers/transformers tokenizer if available, else tiktoken fallback."""
        tok = self._get_tokenizer()
        if tok is not None:
            try:
                return len(tok(text)["input_ids"])
            except Exception:
                pass

        if self._cl100k_fallback is None:
            import tiktoken

            self._cl100k_fallback = tiktoken.get_encoding("cl100k_base")
        return len(self._cl100k_fallback.encode(text, disallowed_special=()))

    def _get_st_model(self) -> Any:
        # Model henüz belleğe alınmadıysa ilk çağrıda yüklenir (Lazy Loading).
        if self._st_model is None:
            try:
                # Neden dosyanın en tepesinde import etmiyoruz?
                # Çünkü sentence-transformers devasa bir PyTorch kütüphanesidir (~2 GB).
                # Kullanıcı sadece OpenAI veya Gemini kullanacaksa servisi gereksiz yormasın,
                # sadece bu yerel mod çağrıldığında dinamik olarak içeriye alınsın.
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
        # Multilingual-E5 modeli dokümanları embed ederken 'passage: ' önekini şart koşar.
        # Bu önek olmazsa model dokümanı doğru vektör uzayına yerleştiremez.
        if self.is_e5 and not text.startswith("passage: "):
            return f"passage: {text}"
        return text

    def _apply_query_prefix(self, text: str) -> str:
        # Multilingual-E5 modeli arama sorgularını embed ederken 'query: ' önekini şart koşar.
        if self.is_e5 and not text.startswith("query: "):
            return f"query: {text}"
        return text

    def embed_documents(self, texts: Sequence[str]) -> np.ndarray:
        if not texts:
            return np.empty((0, self._dimensions), dtype=np.float32)

        # Boş string ("") veya sadece boşluk ("   ") içeren hatalı chunk'ları filtrele
        validate_non_empty_texts(texts)

        # Gerekli ise dokümanlara 'passage: ' önekini ekle
        prefixed_texts = [self._apply_doc_prefix(t) for t in texts]

        # Token limit kontrolü: Modeller sessizce metni kesmemeli (truncate etmemeli)
        for idx, t in enumerate(prefixed_texts):
            c_tokens = self.count_tokens(t)
            if c_tokens > self._max_input_tokens:
                raise ValueError(
                    f"Text at index {idx} has {c_tokens} tokens, exceeding max_input_tokens={self._max_input_tokens}. "
                    f"Embedders must not truncate silently."
                )

        all_vectors: list[list[float]] = []

        if self.client is not None:
            # 1. YOL: Harici yerel HTTP sunucusu (Ollama, vLLM) üzerinden batching & retry ile çağır
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
            # 2. YOL: Python process'i içinde yerel sentence-transformers modeliyle doğrudan CPU/GPU'da hesapla
            st_model = self._get_st_model()
            matrix = st_model.encode(
                prefixed_texts,
                batch_size=self.config.batch_size,
                convert_to_numpy=True,
                show_progress_bar=False,
            ).astype(np.float32)

        # Matryoshka Boyut Kısaltma: Eğer istenen boyut modelin doğal boyutundan küçükse
        # ilk N boyutu alıp (slice) tekrar normalize ediyoruz.
        if self.config.dimensions is not None and matrix.shape[1] > self.config.dimensions:
            matrix = matrix[:, : self.config.dimensions]

        # Cosine similarity aramalarında iç çarpım (dot product) yapabilmek için vektörleri L2-normalize et
        if self.config.normalize:
            return l2_normalize(matrix)
        return matrix

    def embed_query(self, text: str) -> np.ndarray:
        validate_non_empty_texts([text])

        # Gerekli ise sorgunun başına 'query: ' önekini ekle
        prefixed_query = self._apply_query_prefix(text)

        c_tokens = self.count_tokens(prefixed_query)
        if c_tokens > self._max_input_tokens:
            raise ValueError(
                f"Query has {c_tokens} tokens, exceeding max_input_tokens={self._max_input_tokens}. "
                f"Embedders must not truncate silently."
            )

        if self.client is not None:
            # Harici yerel HTTP sunucusu üzerinden sorguyu embed et
            kwargs: dict[str, Any] = {
                "model": self.config.model,
                "input": [prefixed_query],
            }
            if self.config.dimensions is not None:
                kwargs["dimensions"] = self.config.dimensions
            response = with_retry(lambda: self.client.embeddings.create(**kwargs))
            vec = np.array(response.data[0].embedding, dtype=np.float32)
        else:
            # Process-içi sentence-transformers modeli ile sorguyu hesapla
            st_model = self._get_st_model()
            vec = st_model.encode(
                prefixed_query,
                convert_to_numpy=True,
                show_progress_bar=False,
            ).astype(np.float32)

        # Matryoshka Boyut Kısaltma (Query)
        if self.config.dimensions is not None and vec.shape[0] > self.config.dimensions:
            vec = vec[: self.config.dimensions]

        if self.config.normalize:
            return l2_normalize(vec)
        return vec

