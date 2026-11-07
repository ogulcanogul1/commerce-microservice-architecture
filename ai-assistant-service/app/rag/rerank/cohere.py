import logging
import time
from collections.abc import Sequence
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
    - 429 ve 5xx hatalarında 1 kez retry (toplam 2 deneme).
    - 4xx (429 hariç) hatalarda fail-fast (retry yok).
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

        # 1 ilk deneme + 1 retry (maksimum 2 deneme)
        max_attempts = 2
        last_exc: Exception | None = None

        for attempt in range(1, max_attempts + 1):
            try:
                with httpx.Client(timeout=self.timeout_sec, transport=self._transport) as client:
                    response = client.post(COHERE_RERANK_URL, json=payload, headers=headers)

                if response.status_code == 200:
                    data = response.json()
                    raw_results = data.get("results", [])
                    results = [
                        RerankResult(index=int(r["index"]), score=float(r["relevance_score"]))
                        for r in raw_results
                    ]
                    # Azalan skor, eşitlikte orijinal sıra
                    sorted_results = sorted(results, key=lambda r: (-r.score, r.index))
                    validate_rerank_results(sorted_results, n)
                    return sorted_results

                # 4xx (429 hariç) hatalar kalıcı istemci hatalarıdır, tekrar denenmez
                if 400 <= response.status_code < 500 and response.status_code != 429:
                    raise RerankError(
                        f"Cohere Rerank API istemci hatası (HTTP {response.status_code})"
                    )

                # 429 veya 5xx hatası
                raise RerankError(f"Cohere Rerank API sunucu hatası (HTTP {response.status_code})")

            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                last_exc = RerankError(f"Cohere Rerank API ağ hatası: {type(exc).__name__}")
            except RerankError as exc:
                last_exc = exc
                # İstemci hatasıysa döngüyü hemen kır, bekleme
                if "istemci hatası" in str(exc):
                    raise exc
            except Exception as exc:
                last_exc = RerankError(f"Cohere Rerank beklenmeyen hata: {type(exc).__name__}")

            if attempt < max_attempts:
                time.sleep(0.5)

        raise last_exc or RerankError("Cohere Rerank çağrısı başarısız oldu")
