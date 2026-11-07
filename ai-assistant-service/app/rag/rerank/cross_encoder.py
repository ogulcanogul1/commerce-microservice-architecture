import logging
import threading
from collections.abc import Sequence
from typing import Any
from app.rag.rerank.base import Reranker
from app.rag.rerank.models import RerankError, RerankResult, validate_rerank_results

logger = logging.getLogger(__name__)

DEFAULT_CROSS_ENCODER_MODEL = "BAAI/bge-reranker-v2-m3"


class CrossEncoderReranker(Reranker):
    """Yerel sentence-transformers tabanlı Cross-Encoder reranker.

    Özellikler:
    - Tembel yükleme (Lazy loading): Model ilk rerank çağrısında yüklenir.
    - Thread-safe: Model yüklemesi ve predict çağrıları threading.Lock altında sıralanır.
    - Ağ gerektirmez, veri dışarı çıkmaz.
    - NOT: RAG_RERANK_TIMEOUT_SEC yerel modelde uygulanmaz (yerel CPU/GPU çağrısı kesilemez).
    """

    def __init__(
        self,
        model_name: str = "",
        max_length: int = 512,
        batch_size: int = 16,
        device: str | None = None,
    ) -> None:
        self.model_name = model_name.strip() if model_name.strip() else DEFAULT_CROSS_ENCODER_MODEL
        self.max_length = max_length
        self.batch_size = batch_size
        self.device = device
        self.model_id = f"cross_encoder/{self.model_name}"

        self._model: Any = None
        self._load_lock = threading.Lock()
        self._predict_lock = threading.Lock()

    def _get_model(self) -> Any:
        """Modeli ilk kullanımda tembel (lazy) ve thread-safe olarak yükler."""
        if self._model is not None:
            return self._model

        with self._load_lock:
            if self._model is not None:
                return self._model

            try:
                from sentence_transformers import CrossEncoder
            except ImportError as exc:
                raise RerankError(
                    "sentence-transformers kütüphanesi kurulu değil. "
                    "Yerel cross-encoder reranker kullanmak için 'uv sync --extra local-embedding' çalıştırın."
                ) from exc

            try:
                logger.info("Yerel CrossEncoder modeli yükleniyor: %s", self.model_name)
                self._model = CrossEncoder(
                    self.model_name,
                    max_length=self.max_length,
                    device=self.device,
                )
                return self._model
            except Exception as exc:
                raise RerankError(
                    f"CrossEncoder modeli ({self.model_name}) yüklenemedi: {type(exc).__name__}"
                ) from exc

    def warmup(self) -> None:
        """Uygulama başlangıcında modeli yükleyip tek bir duman tahmini ile ısıtır."""
        self._get_model()
        self.rerank("warmup query", ["warmup document"])

    def rerank(self, query: str, documents: Sequence[str]) -> list[RerankResult]:
        docs_list = list(documents)
        n = len(docs_list)
        if n == 0:
            return []

        model = self._get_model()
        pairs = [[query, doc] for doc in docs_list]

        try:
            with self._predict_lock:
                scores = model.predict(pairs, batch_size=self.batch_size)
        except Exception as exc:
            raise RerankError(f"CrossEncoder rerank çağrısı başarısız: {type(exc).__name__}") from exc

        # Skorlar numpy array veya liste gelebilir
        results = [RerankResult(index=i, score=float(scores[i])) for i in range(n)]

        # Skora göre azalan, eşitlikte orijinal sırayı koruyan kararlı sıralama
        sorted_results = sorted(results, key=lambda r: (-r.score, r.index))
        validate_rerank_results(sorted_results, n)
        return sorted_results
