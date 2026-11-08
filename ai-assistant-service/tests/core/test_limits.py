"""Eşzamanlılık sınırı (ConcurrencyLimiter), gövde boyutu (BodySizeLimitMiddleware)
ve RFC 7807 hata hiyerarşisi birim testleri.
"""

from __future__ import annotations

import asyncio
import pytest
from starlette.requests import Request
from starlette.responses import PlainTextResponse

from app.core.errors import (
    NonRetryableException,
    ProblemDetails,
    ProblemType,
    RetryableException,
)
from app.core.limits import (
    BodySizeLimitMiddleware,
    ConcurrencyLimiter,
    Overloaded,
)


# ---------------------------------------------------------------------------
# ConcurrencyLimiter Testleri
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_concurrency_limiter_allows_up_to_max():
    """Limiter belirlenen kapasiteye kadar slot tahsis eder."""
    limiter = ConcurrencyLimiter(max_concurrent=2)
    assert limiter.available_slots == 2
    assert limiter.current_count == 0

    async with limiter.slot():
        assert limiter.current_count == 1
        assert limiter.available_slots == 1

        async with limiter.slot():
            assert limiter.current_count == 2
            assert limiter.available_slots == 0

            # 3. istek geldiğinde kuyruğa almadan anında Overloaded fırlatmalı
            with pytest.raises(Overloaded) as exc_info:
                async with limiter.slot():
                    pass

            assert exc_info.value.status_code == 503
            assert exc_info.value.retryable is True
            assert exc_info.value.retry_after_seconds == 5
            assert exc_info.value.headers.get("Retry-After") == "5"

    # Slotlar çıkışta eksiksiz serbest bırakılmalıdır
    assert limiter.current_count == 0
    assert limiter.available_slots == 2


@pytest.mark.anyio
async def test_concurrency_limiter_releases_on_exception():
    """İşlem hata fırlatsa bile finally bloğu sayacı sızdırmadan azaltmalıdır."""
    limiter = ConcurrencyLimiter(max_concurrent=1)

    with pytest.raises(RuntimeError):
        async with limiter.slot():
            raise RuntimeError("LLM bağlantı koptu")

    # Sayaç sızıntısı olmamalı, tekrar slot alınabilmeli
    assert limiter.current_count == 0
    async with limiter.slot():
        assert limiter.current_count == 1


@pytest.mark.anyio
async def test_concurrency_limiter_exact_concurrent_races():
    """10 eşzamanlı istek aynı anda geldiğinde tam 3'ü geçmeli, 7'si Overloaded almalıdır."""
    limiter = ConcurrencyLimiter(max_concurrent=3)
    barrier = asyncio.Event()

    passed = 0
    overloaded = 0

    async def worker():
        nonlocal passed, overloaded
        try:
            async with limiter.slot():
                passed += 1
                await barrier.wait()  # Tüm worker'lar aynı anda slotta beklesin
        except Overloaded:
            overloaded += 1

    tasks = [asyncio.create_task(worker()) for _ in range(10)]
    # Task'ların çalışması için yield et
    await asyncio.sleep(0.01)

    # Bariyeri aç ve işlemler tamamlansın
    barrier.set()
    await asyncio.gather(*tasks)

    assert passed == 3
    assert overloaded == 7
    assert limiter.current_count == 0


def test_concurrency_limiter_invalid_capacity():
    """Kapasite en az 1 olmalıdır."""
    with pytest.raises(ValueError, match="en az 1"):
        ConcurrencyLimiter(max_concurrent=0)


# ---------------------------------------------------------------------------
# BodySizeLimitMiddleware Testleri
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_body_size_middleware_blocks_oversized_post():
    """Content-Length limiti aşan POST isteklerini 413 ile reddeder."""
    async def dummy_app(scope, receive, send):
        response = PlainTextResponse("OK")
        await response(scope, receive, send)

    middleware = BodySizeLimitMiddleware(dummy_app, max_bytes=100)

    # 150 baytlık POST isteği simülasyonu
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/v1/chat",
        "headers": [(b"content-length", b"150")],
    }

    sent_messages = []
    async def fake_send(msg):
        sent_messages.append(msg)

    async def fake_receive():
        return {"type": "http.request", "body": b""}

    await middleware(scope, fake_receive, fake_send)

    # İlk gönderilen mesaj http.response.start ve status 413 olmalıdır
    assert sent_messages[0]["type"] == "http.response.start"
    assert sent_messages[0]["status"] == 413


@pytest.mark.anyio
async def test_body_size_middleware_allows_normal_post_and_get():
    """Normal boyutlu POST ve GET istekleri filtreden geçer."""
    async def dummy_app(scope, receive, send):
        response = PlainTextResponse("OK")
        await response(scope, receive, send)

    middleware = BodySizeLimitMiddleware(dummy_app, max_bytes=1000)

    # 50 baytlık POST
    scope_post = {
        "type": "http",
        "method": "POST",
        "path": "/api/v1/chat",
        "headers": [(b"content-length", b"50")],
    }
    sent_messages = []
    async def fake_send(msg):
        sent_messages.append(msg)

    async def fake_receive():
        return {"type": "http.request", "body": b""}

    await middleware(scope_post, fake_receive, fake_send)
    assert sent_messages[0]["status"] == 200

    # GET isteği (Content-Length olmasa da geçer)
    scope_get = {
        "type": "http",
        "method": "GET",
        "path": "/health",
        "headers": [],
    }
    sent_messages = []
    await middleware(scope_get, fake_receive, fake_send)
    assert sent_messages[0]["status"] == 200


# ---------------------------------------------------------------------------
# RFC 7807 Hata Modeli ve Semantik Testleri
# ---------------------------------------------------------------------------

def test_problem_details_retryable_semantics():
    """ProblemDetails modeli retryable semantiğini ve serialization kurallarını korur."""
    p1 = ProblemDetails(
        type=ProblemType.AI_OVERLOADED.value,
        title="Service Overloaded",
        status=503,
        detail="Sunucu meşgul",
        retryable=True,
        retry_after_seconds=5,
    )
    dumped = p1.model_dump(exclude_none=True)
    assert dumped["retryable"] is True
    assert dumped["retry_after_seconds"] == 5
    assert dumped["type"] == ProblemType.AI_OVERLOADED.value

    # NonRetryable hatada retry_after_seconds None olduğu için exclude_none ile serileşmez
    p2 = ProblemDetails(
        title="Bad Request",
        status=400,
        detail="Hatalı girdi",
        retryable=False,
    )
    dumped2 = p2.model_dump(exclude_none=True)
    assert dumped2["retryable"] is False
    assert "retry_after_seconds" not in dumped2


def test_exception_classes_retryable_flag():
    """RetryableException ve NonRetryableException doğru sınıf bayraklarını taşır."""
    non_retry = NonRetryableException(status_code=400, detail="Hata")
    assert non_retry.retryable is False

    retry = RetryableException(status_code=503, detail="Aşırı yük", retry_after_seconds=10)
    assert retry.retryable is True
    assert retry.retry_after_seconds == 10
    assert retry.headers["Retry-After"] == "10"
