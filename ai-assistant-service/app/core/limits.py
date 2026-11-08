"""Süreç içi eşzamanlılık (concurrency) ve istek gövdesi boyutu sınırlama mekanizmaları.

Dağıtık Sistem Kuralı (Fail-Fast):
LLM çağrıları uzun süreli (10-45s) ve yüksek maliyetli olduğundan istekler kuyrukta bekletilmez.
Aktif kapasite dolduğunda anında 503 Overloaded (Retry-After: 5) fırlatılır.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
import logging
from typing import AsyncIterator

from fastapi import Request
from starlette.datastructures import Headers
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from app.core.errors import ProblemDetails, ProblemType, RetryableException

logger = logging.getLogger(__name__)


class Overloaded(RetryableException):
    """Süreç içi maksimum eşzamanlı LLM istek sınırına ulaşıldığında fırlatılan istisna.
    
    RetryableException'dan türer; bu sayede:
    - retryable: True olur (istemciye 'bu geçici bir durumdur' der).
    - HTTP 'Retry-After: 5' başlığını otomatik ekler (5 saniye beklemesini söyler).
    - RFC 7807 type: 'https://api.commerce.com/errors/ai-overloaded' olarak işaretlenir.
    """

    def __init__(
        self,
        detail: str = "Asistan servisi şu anda maksimum eşzamanlı kapasiteye ulaştı. Lütfen birkaç saniye sonra tekrar deneyin.",
        *,
        retry_after_seconds: int = 5,
    ) -> None:
        # Üst sınıf olan RetryableException'ı başlatıyoruz
        super().__init__(
            status_code=503,
            detail=detail,
            problem_type=ProblemType.AI_OVERLOADED,
            title="Service Overloaded",
            retry_after_seconds=retry_after_seconds,
        )


class ConcurrencyLimiter:
    """Süreç bazlı, kuyruksuz ve non-blocking eşzamanlılık denetleyicisi.
    
    Neden Semaphore veya Kuyruk Değil?
    Kuyruk kullanırsak, 100 istek arka arkaya geldiğinde son istekler dakikalarca bekler,
    bellek şişer ve istemci çoktan vazgeçtiği halde arkada gereksiz token faturası üretilir.
    Bu sınıf kapasite doluysa sıraya ALMAZ, anında Overloaded fırlatır (Fast-Fail).
    """

    def __init__(self, max_concurrent: int) -> None:
        # En az 1 eşzamanlı işleme izin verilmelidir
        if max_concurrent < 1:
            raise ValueError("max_concurrent en az 1 olmalıdır.")
        self.max_concurrent = max_concurrent

        # O anda sunucuda kaç tane LLM isteğinin aktif olarak çalıştığını tutan sayaç
        self._current_count = 0

        # Sayaç artırma/azaltma işlemlerinin atomik olması için asenkron kilit
        self._lock = asyncio.Lock()

    @property
    def current_count(self) -> int:
        """Şu anda aktif olarak çalışan işlem sayısı."""
        return self._current_count

    @property
    def available_slots(self) -> int:
        """Kalan boş slot sayısı."""
        return max(0, self.max_concurrent - self._current_count)

    @asynccontextmanager
    async def slot(self) -> AsyncIterator[None]:
        """İşlem için bir slot rezerve eden asenkron context manager.
        
        Kullanım:
            async with limiter.slot():
                await llm_call()  # Sadece slot alındığında burası çalışır
        """
        # 1. Adım: Kilidi al ve mevcut kapasiteyi kontrol et
        async with self._lock:
            # Eğer aktif istek sayısı sınıra ulaştıysa veya aştıysa kuyruğa alma, anında reddet!
            if self._current_count >= self.max_concurrent:
                logger.warning(
                    "Maksimum eşzamanlı istek limitine ulaşıldı: %d/%d (İstek reddedildi)",
                    self._current_count,
                    self.max_concurrent,
                )
                raise Overloaded()

            # Slot müsait, sayacı 1 artırıyoruz
            self._current_count += 1

        # 2. Adım: Çağıran bloğun (LLM işleminin) çalışmasına izin ver
        try:
            yield
        finally:
            # 3. Adım: İşlem başarılı olsa da, hata fırlatsa da sayacı MUTLAKA 1 azalt (kaynak sızıntısını önle)
            async with self._lock:
                self._current_count -= 1


class BodySizeLimitMiddleware:
    """İstek gövdesi (payload) boyutunu denetleyen saf ASGI Middleware.
    
    Güvenlik Amacı:
    Kötü niyetli kullanıcıların 50 MB gibi devasa istekler yollayarak sunucu RAM'ini tüketmesini (OOM) engeller.
    Gövdeyi belleğe hiç okumadan (stream tüketmeden) Content-Length başlığından kontrol eder.
    """

    def __init__(self, app: ASGIApp, max_bytes: int) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        # Yalnızca HTTP isteklerini denetle (WebSocket veya Lifespan olayları filtreden geçsin)
        if scope["type"] == "http":
            method = scope.get("method", "GET").upper()

            # Yalnızca gövde taşıyabilen POST, PUT, PATCH isteklerini kontrol et (GET isteklerinde gövde aranmaz)
            if method in {"POST", "PUT", "PATCH"}:
                headers = Headers(scope=scope)
                content_length_header = headers.get("content-length")

                if content_length_header is not None:
                    try:
                        content_length = int(content_length_header)

                        # Eğer istek gövdesi izin verilen bayt sınırından büyükse:
                        if content_length > self.max_bytes:
                            logger.warning(
                                "İstek gövdesi boyut sınırı aşıldı: %d bayt > %d bayt",
                                content_length,
                                self.max_bytes,
                            )

                            # RFC 7807 uyumlu 413 Payload Too Large yanıtı oluştur
                            problem = ProblemDetails(
                                type=ProblemType.BLANK.value,
                                title="Payload Too Large",
                                status=413,
                                detail=f"İstek gövdesi izin verilen maksimum boyuttan büyük ({content_length} > {self.max_bytes} bayt).",
                                instance=scope.get("path"),
                                retryable=False,  # İstek gövdesi küçültülmeden tekrar denenemez
                            )

                            response = JSONResponse(
                                status_code=413,
                                content=problem.model_dump(exclude_none=True),
                                media_type="application/problem+json",
                            )

                            # Yanıtı doğrudan ASGI protokolü üzerinden istemciye gönder ve isteği sonlandır
                            await response(scope, receive, send)
                            return
                    except ValueError:
                        # Sayıya çevrilemeyen geçersiz bir Content-Length başlığı varsa kontrolü FastAPI'ye bırak
                        pass

        # Limit aşımı yoksa veya güvenliyse isteğin sıradaki middleware'e veya endpoint'e geçmesine izin ver
        await self.app(scope, receive, send)


def get_ai_limiter(request: Request) -> ConcurrencyLimiter:
    """FastAPI endpoint'lerinde 'limiter: ConcurrencyLimiter = Depends(get_ai_limiter)'
    şeklinde app.state üzerindeki ortak limiter nesnesine erişmeyi sağlayan bağımlılık.
    """
    limiter = getattr(request.app.state, "ai_limiter", None)
    if limiter is None:
        # Test ortamlarında veya izole çağrılarda lifespan çalışmamışsa koruma amaçlı varsayılan bir nesne üret
        limiter = ConcurrencyLimiter(max_concurrent=20)
        request.app.state.ai_limiter = limiter
    return limiter
