"""RequestContextMiddleware ve Asenkron Correlation ID Bağlamı Testleri.

Bu test modülü:
1. RequestContextMiddleware'in X-Correlation-Id başlığını temizleyip ContextVar'a yazdığını ve istek
   bitince bağlamı sıfırladığını doğrular.
2. CRLF log enjeksiyonu ve aşırı uzunluktaki manipülatif başlıkların ayıklandığını kontrol eder.
3. Python `asyncio.to_thread` ve `asyncio.create_task` çağrılarında ContextVar'ın kopyalandığını garantiler.
4. Statik kod taraması ile `app/` altında `run_in_executor` veya `ThreadPoolExecutor` kullanılıyorsa
   mutlaka `copy_context` kullanıldığını zorunlu kılar (Plan 1.6 - Asenkron Bağlam Kaybı Koruması).
"""

import asyncio
from pathlib import Path
import pytest
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.testclient import TestClient

from app.observability.context import RequestContextMiddleware, correlation_id_var


def _create_test_app():
    """ContextVar değerini yanıt olarak dönen minimal bir test ASGI uygulaması."""
    async def app(scope, receive, send):
        if scope["type"] == "http":
            req = Request(scope, receive)
            captured_id = correlation_id_var.get()
            resp = JSONResponse({"correlation_id": captured_id})
            await resp(scope, receive, send)

    # Middleware'i test uygulamasına sar
    return RequestContextMiddleware(app)


def test_middleware_captures_valid_correlation_id_and_resets():
    """Geçerli bir X-Correlation-Id gönderildiğinde context'e yazıldığını ve

    istek bittikten sonra context'in sıfırlandığını (None olduğunu) doğrular.
    """
    app = _create_test_app()
    client = TestClient(app)

    # 1. İstek öncesi bağlam boş olmalı
    assert correlation_id_var.get() is None

    # 2. İstek at ve endpoint içindeki yakalanan değeri kontrol et
    response = client.get("/", headers={"x-correlation-id": "test-corr-1234"})
    assert response.status_code == 200
    assert response.json()["correlation_id"] == "test-corr-1234"

    # 3. İstek tamamlandıktan sonra finally bloğunun çalıştığını ve bağlamın sıfırlandığını doğrula
    assert correlation_id_var.get() is None


def test_middleware_sanitizes_crlf_and_oversized_ids():
    """Satır sonu (\n, \r) içeren log enjeksiyonu denemelerini ve aşırı uzun değerleri

    temizleyip None yaptığını doğrular.
    """
    app = _create_test_app()
    client = TestClient(app)

    # CRLF satır sonu içeren kötü niyetli header
    resp_crlf = client.get("/", headers={"x-correlation-id": "corr-123\nInjected-Log"})
    assert resp_crlf.status_code == 200
    assert resp_crlf.json()["correlation_id"] is None

    # 64 karakterden uzun manipüle edilmiş header
    oversized = "a" * 70
    resp_long = client.get("/", headers={"x-correlation-id": oversized})
    assert resp_long.status_code == 200
    assert resp_long.json()["correlation_id"] is None


@pytest.mark.anyio
async def test_async_context_propagation_to_thread_and_task():
    """ContextVar değerinin asyncio.to_thread ve asyncio.create_task çağrılarına

    kayıpsız şekilde kopyalandığını (propagation) doğrular.
    """
    token = correlation_id_var.set("c-async-test")
    try:
        # 1. asyncio.to_thread (ThreadPool'a bağlam kopyalama kontrolü)
        def thread_worker():
            return correlation_id_var.get()

        thread_result = await asyncio.to_thread(thread_worker)
        assert thread_result == "c-async-test", "to_thread içinde ContextVar değeri korunmalıdır!"

        # 2. asyncio.create_task (Yeni alt task'e bağlam kopyalama kontrolü)
        async def task_worker():
            return correlation_id_var.get()

        task = asyncio.create_task(task_worker())
        task_result = await task
        assert task_result == "c-async-test", "create_task içinde ContextVar değeri korunmalıdır!"
    finally:
        correlation_id_var.reset(token)


def test_static_guard_against_unhandled_run_in_executor():
    """app/ dizini altındaki hiçbir Python dosyasında copy_context olmadan

    run_in_executor veya ThreadPoolExecutor kullanılmadığını statik olarak doğrular.
    Gerekçe: loop.run_in_executor ContextVar'ı kopyalamaz; kullanılırsa copy_context şarttır.
    """
    app_dir = Path(__file__).resolve().parent.parent.parent / "app"
    violations: list[str] = []

    for py_file in app_dir.rglob("*.py"):
        content = py_file.read_text(encoding="utf-8")
        has_executor = "run_in_executor" in content or "ThreadPoolExecutor" in content
        has_context_copy = "copy_context" in content

        if has_executor and not has_context_copy:
            violations.append(
                f"{py_file.name}: 'run_in_executor' veya 'ThreadPoolExecutor' kullanılmış fakat "
                f"'copy_context' bulunamadı (ContextVar kaybı riski, bkz. plan 1.6)."
            )

    assert not violations, "\n".join(violations)
