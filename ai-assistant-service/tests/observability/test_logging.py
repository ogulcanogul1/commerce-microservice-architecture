"""Loglama Altyapısı, JSON Formatlayıcı ve PII Maskeleme Birim Testleri.

Bu test modülü:
1. JsonLogFormatter'ın tek satır geçerli JSON ürettiğini,
2. Formatter seviyesinde telefon, e-posta gibi kişisel verilerin (PII) otomatik maskelendiğini,
3. Exception (traceback) loglarının tek satır JSON alanına indirgendiğini ve hata içindeki PII'ların maskelendiğini,
4. Aktif OTel span'i varken traceId ve spanId'nin eklendiğini, span yokken alanların bulunmadığını,
5. ContextVar'daki correlationId'nin log JSON'una basıldığını,
6. AccessLogNoiseFilter'ın probe/scrape access loglarını elediğini doğrular.
"""

import io
import json
import logging
import pytest
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from app.core.config import settings
from app.observability.context import correlation_id_var
from app.observability.logging import (
    AccessLogNoiseFilter,
    JsonLogFormatter,
    TraceContextFilter,
)
from app.observability.tracing import build_tracer_provider


def _setup_test_logger(name: str = "test.logger") -> tuple[logging.Logger, io.StringIO]:
    """Testler için belleğe yazan (io.StringIO) izole bir Logger hazırlar."""
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.addFilter(TraceContextFilter())
    handler.setFormatter(JsonLogFormatter())

    logger = logging.getLogger(name)
    logger.handlers = [handler]
    logger.setLevel(logging.INFO)
    logger.propagate = False
    return logger, stream


def test_json_log_formatter_basic_fields():
    """Temel bir info logunun geçerli tek satır JSON ürettiğini ve zorunlu alanları içerdiğini doğrular."""
    logger, stream = _setup_test_logger("test.basic")
    logger.info("Sistem başarıyla başlatıldı.")

    raw_output = stream.getvalue().strip()
    # Çıktının tek satır olduğunu kontrol et
    assert "\n" not in raw_output

    data = json.loads(raw_output)
    assert data["level"] == "info"
    assert data["service"] == settings.SERVICE_NAME
    assert data["logger"] == "test.basic"
    assert data["message"] == "Sistem başarıyla başlatıldı."
    assert "timestamp" in data
    # Span ve correlation olmadığı için bu alanlar JSON'da yer almamalı
    assert "traceId" not in data
    assert "spanId" not in data
    assert "correlationId" not in data


def test_json_log_formatter_pii_masking():
    """Log mesajı içine yazılan telefon ve e-posta gibi kişisel verilerin maskelendiğini doğrular."""
    logger, stream = _setup_test_logger("test.pii")
    logger.info("Müşteri telefon: 0532 111 22 33 ve e-posta: musteri@example.com")

    data = json.loads(stream.getvalue().strip())
    # Orijinal hassas veriler log çıktısında kesinlikle bulunmamalı
    assert "0532 111 22 33" not in data["message"]
    assert "musteri@example.com" not in data["message"]
    # mask_pii'nin ürettiği standart etiketler yer almalı
    assert "[TELEFON]" in data["message"]
    assert "[EPOSTA]" in data["message"]


def test_json_log_formatter_exception_single_line_and_pii_masked():
    """Hata loglarının tek satır JSON olduğunu, stack_trace alanına yazıldığını

    ve stack trace içindeki PII verilerinin de maskelendiğini doğrular.
    """
    logger, stream = _setup_test_logger("test.exception")

    try:
        # PII içeren bir fonksiyon çağrısı simülasyonu
        sensitive_arg = "0532 999 88 77"
        raise ValueError(f"Hatalı parametre: {sensitive_arg}")
    except ValueError:
        logger.exception("İşlem sırasında beklenmedik hata oluştu")

    raw_output = stream.getvalue().strip()
    # Stack trace çok satırlı olmasına rağmen JSON çıktısı tek satır olmalı
    assert "\n" not in raw_output

    data = json.loads(raw_output)
    assert data["level"] == "error"
    assert "stack_trace" in data
    assert "ValueError: Hatalı parametre:" in data["stack_trace"]
    # Stack trace içindeki telefon da maskelenmiş olmalı
    assert "0532 999 88 77" not in data["stack_trace"]
    assert "[TELEFON]" in data["stack_trace"]


def test_json_log_formatter_stack_info_captured_and_masked():
    """stack_info=True ile loglandığında stack_trace alanının oluştuğunu ve PII maskelendiğini doğrular."""
    logger, stream = _setup_test_logger("test.stack_info")
    logger.info("Yığın izi kaydı (telefon: 0532 555 44 33)", stack_info=True)

    raw_output = stream.getvalue().strip()
    assert "\n" not in raw_output
    data = json.loads(raw_output)

    assert "stack_trace" in data
    assert "0532 555 44 33" not in data["stack_trace"]
    assert "[TELEFON]" in data["message"]


def test_json_log_formatter_trace_context_fields():
    """Aktif bir OpenTelemetry span'i içindeyken traceId ve spanId alanlarının

    doğru hex formatında eklendiğini doğrular.
    """
    provider = build_tracer_provider(SimpleSpanProcessor(InMemorySpanExporter()))
    tracer = provider.get_tracer("test-tracer")

    logger, stream = _setup_test_logger("test.trace")

    with tracer.start_as_current_span("agent-chat-span"):
        logger.info("Span içinde işlem yapılıyor")

    data = json.loads(stream.getvalue().strip())
    assert "traceId" in data
    assert "spanId" in data
    # traceId 32 karakterlik hex, spanId 16 karakterlik hex olmalı
    assert len(data["traceId"]) == 32
    assert len(data["spanId"]) == 16
    int(data["traceId"], 16)  # Geçerli hex doğrulaması
    int(data["spanId"], 16)

    provider.shutdown()


def test_json_log_formatter_correlation_id_field():
    """ContextVar içinde aktif bir correlation ID varken JSON çıktısına basıldığını doğrular."""
    logger, stream = _setup_test_logger("test.corr")

    token = correlation_id_var.set("c-test-corr-987")
    try:
        logger.info("Correlation ID testi")
    finally:
        correlation_id_var.reset(token)

    data = json.loads(stream.getvalue().strip())
    assert data.get("correlationId") == "c-test-corr-987"


def test_access_log_noise_filter():
    """AccessLogNoiseFilter'ın probe ve scrape loglarını elediğini, normal istekleri geçirdiğini doğrular."""
    noise_filter = AccessLogNoiseFilter()

    # 1. Gürültü logları (sağlık kontrolleri ve metrik scrape) elenmeli (False dönmeli)
    record_health = logging.LogRecord(
        name="uvicorn.access", level=logging.INFO, pathname="", lineno=0,
        msg='127.0.0.1:1234 - "GET /health HTTP/1.1" 200 OK', args=(), exc_info=None
    )
    assert noise_filter.filter(record_health) is False

    record_scrape = logging.LogRecord(
        name="uvicorn.access", level=logging.INFO, pathname="", lineno=0,
        msg='127.0.0.1:1234 - "GET /actuator/prometheus HTTP/1.1" 200 OK', args=(), exc_info=None
    )
    assert noise_filter.filter(record_scrape) is False

    # 2. Gerçek iş isteği filtreden geçmeli (True dönmeli)
    record_chat = logging.LogRecord(
        name="uvicorn.access", level=logging.INFO, pathname="", lineno=0,
        msg='127.0.0.1:1234 - "POST /agent/chat HTTP/1.1" 200 OK', args=(), exc_info=None
    )
    assert noise_filter.filter(record_chat) is True
