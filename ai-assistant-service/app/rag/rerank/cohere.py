import logging
import time
from collections.abc import Sequence
from typing import Any
import httpx
from app.core.config import get_settings
from app.rag.rerank.base import Reranker
from app.rag.rerank.models import RerankError, RerankResult, validate_rerank_results

logger = logging.getLogger(__name__)

DEFAULT_COHERE_RERANK_MODEL = "rerank-v3.5"
COHERE_RERANK_URL = "https://api.cohere.com/v2/rerank"


class CohereReranker(Reranker):
    """Cohere v2 Rerank REST API sağlayıcısı.

    Özellikler:
    - HTTPX üzerinden doğrudan REST çağrısı (ek SDK bağımlılığı yok).
    - Paylaşılan ve yeniden kullanılan tekil httpx.Client örneği.
    - Toplam zaman aşımı bütçesi (tüm denemeler dahil toplam süre self.timeout_sec'i aşamaz).
    - 429 ve 5xx hatalarında 1 kez retry (toplam 2 deneme).
    - 4xx (429 hariç) hatalarda ve bozuk 200 yanıtlarında fail-fast (retry yok).
    - Hata mesajlarında API anahtarı, soru veya doküman metinleri sızdırılmaz.
    """

    def __init__(
        self,
        api_key: str = "",
        model_name: str = "",
        timeout_sec: float | None = None,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        settings = get_settings()
        self.api_key = api_key.strip() or settings.COHERE_API_KEY.strip()
        if not self.api_key:
            raise ValueError(
                "COHERE_API_KEY tanımlı değil. Cohere reranker kullanmak için API anahtarı gereklidir."
            )

        self.model_name = (
            model_name.strip() or settings.RAG_RERANK_MODEL.strip() or DEFAULT_COHERE_RERANK_MODEL
        )
        self.timeout_sec = (
            timeout_sec if timeout_sec is not None else settings.RAG_RERANK_TIMEOUT_SEC
        )
        self.model_id = f"cohere/{self.model_name}"
        self._transport = transport
        self._client = httpx.Client(timeout=self.timeout_sec, transport=self._transport)

    def close(self) -> None:
        """Paylaşılan HTTP istemcisini kapatır."""
        self._client.close()

    def __enter__(self) -> "CohereReranker":
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()

    def rerank(self, query: str, documents: Sequence[str]) -> list[RerankResult]:
        docs_list = list(documents)
        n = len(docs_list)
        if n == 0:
            return []

        payload = {
            "model": self.model_name,
            "query": query,
            "documents": docs_list,
            "top_n": n,
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "X-Client-Name": "commerce-platform",
        }

        deadline = time.monotonic() + self.timeout_sec
        max_attempts = 2
        last_exc: Exception | None = None

        for attempt in range(1, max_attempts + 1):
            time_left = deadline - time.monotonic()
            if time_left <= 0:
                raise RerankError(
                    f"Cohere Rerank API zaman aşımına uğradı ({self.timeout_sec}s bütçesi aşıldı)"
                )

            try:
                response = self._client.post(
                    COHERE_RERANK_URL,
                    json=payload,
                    headers=headers,
                    timeout=time_left,
                )
            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                last_exc = RerankError(f"Cohere Rerank API ağ hatası: {type(exc).__name__}")
                if attempt < max_attempts:
                    remaining_after_err = deadline - time.monotonic()
                    sleep_time = min(0.5, max(0.0, remaining_after_err))
                    if sleep_time > 0:
                        time.sleep(sleep_time)
                    continue
                break
            except Exception as exc:
                raise RerankError(f"Cohere Rerank beklenmeyen hata: {type(exc).__name__}") from exc

            # 1. 200 OK Başarılı yanıt
            if response.status_code == 200:
                try:
                    data = response.json()
                    raw_results = data.get("results", [])
                    results = [
                        RerankResult(index=int(r["index"]), score=float(r["relevance_score"]))
                        for r in raw_results
                    ]
                    sorted_results = sorted(results, key=lambda r: (-r.score, r.index))
                    validate_rerank_results(sorted_results, n)
                    return sorted_results
                except Exception as exc:
                    # Doğrulama veya format hatası durumunda tekrar deneme, fail-fast sonlandır
                    if isinstance(exc, RerankError):
                        raise
                    raise RerankError(
                        f"Cohere Rerank yanıt işleme hatası: {type(exc).__name__}"
                    ) from exc

            # 2. 4xx Kalıcı istemci hataları (429 hariç) fail-fast
            if 400 <= response.status_code < 500 and response.status_code != 429:
                raise RerankError(
                    f"Cohere Rerank API istemci hatası (HTTP {response.status_code})"
                )

            # 3. 429 Rate limit veya 5xx Sunucu hatası (geçici hata, tekrar denenebilir)
            last_exc = RerankError(
                f"Cohere Rerank API sunucu hatası (HTTP {response.status_code})"
            )

            if attempt < max_attempts:
                remaining_after_err = deadline - time.monotonic()
                sleep_time = min(0.5, max(0.0, remaining_after_err))
                if sleep_time > 0:
                    time.sleep(sleep_time)
                else:
                    break

        raise last_exc or RerankError("Cohere Rerank çağrısı başarısız oldu")
