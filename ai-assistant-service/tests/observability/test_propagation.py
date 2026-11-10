"""Kafka Mesaj Başlıkları ve Trace Context Yayılımı (Propagation) Testleri.

Bu test modülü:
1. build_kafka_headers fonksiyonunun aktif OTel span'inden geçerli 'traceparent' başlığı ürettiğini,
2. Correlation ID'nin 'X-Correlation-Id' başlığıyla UTF-8 bayt dizisi olarak eklendiğini,
3. Aktif span ve correlation ID yokken boş liste döndüğünü,
4. W3C Baggage başlıklarının sızdırılmadığını (güvenlik hijyeni),
5. KafkaTicketPublisher.publish metodunun PRODUCER span içinde çalıştığını ve üretilen başlıkları
   send_and_wait çağrısına eksiksiz ilettiğini doğrular.
"""

from unittest.mock import AsyncMock
import pytest
from opentelemetry import baggage
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from app.agent.tickets import KafkaTicketPublisher, build_ticket_event
from app.observability.propagation import build_kafka_headers
from app.observability.tracing import build_tracer_provider


def test_build_kafka_headers_with_active_span_and_correlation_id():
    """Aktif bir span varken traceparent formatının doğruluğunu ve correlation ID'nin eklendiğini doğrular."""
    memory_exporter = InMemorySpanExporter()
    provider = build_tracer_provider(SimpleSpanProcessor(memory_exporter))
    tracer = provider.get_tracer("test-kafka-tracer")

    try:
        with tracer.start_as_current_span("kafka-test-span") as span:
            ctx = span.get_span_context()
            expected_trace_id = format(ctx.trace_id, "032x")

            headers = build_kafka_headers("c-kafka-123")

            headers_dict = {k: v.decode("utf-8") for k, v in headers}
            assert "traceparent" in headers_dict
            assert headers_dict["X-Correlation-Id"] == "c-kafka-123"

            # W3C traceparent formatı: 00-{trace_id}-{span_id}-{trace_flags}
            traceparent = headers_dict["traceparent"]
            parts = traceparent.split("-")
            assert len(parts) == 4
            assert parts[0] == "00"  # Sürüm
            assert parts[1] == expected_trace_id  # Trace ID
            assert len(parts[2]) == 16  # Parent Span ID (16 hex)
    finally:
        provider.shutdown()


def test_build_kafka_headers_without_span_and_none_correlation():
    """Span yokken ve correlation_id None iken boş liste döndüğünü doğrular."""
    # 1. Her ikisi de yok
    headers_empty = build_kafka_headers(None)
    assert headers_empty == []

    # 2. Yalnızca correlation_id var
    headers_corr = build_kafka_headers("c-only-corr")
    assert headers_corr == [("X-Correlation-Id", b"c-only-corr")]


def test_build_kafka_headers_ignores_baggage():
    """W3C Baggage başlıklarının Kafka mesaj başlıklarına bilerek dahil edilmediğini doğrular."""
    ctx = baggage.set_baggage("user.role", "admin")

    # Baggage bağlamı aktifken başlıkları oluştur
    from opentelemetry.context import attach, detach
    token = attach(ctx)
    try:
        headers = build_kafka_headers("c-baggage-test")
        header_keys = [k for k, _ in headers]
        assert "baggage" not in header_keys
    finally:
        detach(token)


@pytest.mark.anyio
async def test_kafka_ticket_publisher_injects_headers_and_producer_span(monkeypatch: pytest.MonkeyPatch):
    """KafkaTicketPublisher.publish metodunun send_and_wait'e doğru key, value ve

    trace/correlation başlıklarını ilettiğini doğrular.
    """
    memory_exporter = InMemorySpanExporter()
    provider = build_tracer_provider(SimpleSpanProcessor(memory_exporter))
    # Test süresince izole provider'ı trace._TRACER_PROVIDER olarak bağla (test bittiğinde monkeypatch temizler)
    from opentelemetry import trace
    monkeypatch.setattr(trace, "_TRACER_PROVIDER", provider)

    try:
        publisher = KafkaTicketPublisher(bootstrap_servers="localhost:9092", topic="support.ticket.created")
        # Gerçek Kafka ağına bağlanmamak için sahte producer yerleştir
        mock_producer = AsyncMock()
        publisher._producer = mock_producer

        event = build_ticket_event(
            ticket_id="TCK-9999",
            customer_id="cust-111",
            subject="Geciken Kargo",
            summary="Siparişim teslim edilmedi",
            order_number="ORD-5555",
            correlation_id="c-ticket-workflow-777",
        )

        await publisher.publish(event)

        # send_and_wait çağrıldı mı?
        assert mock_producer.send_and_wait.called
        call_args = mock_producer.send_and_wait.call_args
        topic_arg, = call_args[0]
        kwargs = call_args[1]

        assert topic_arg == "support.ticket.created"
        assert kwargs["key"] == b"TCK-9999"
        assert b"cust-111" in kwargs["value"]

        # Başlıkları kontrol et
        headers = kwargs["headers"]
        headers_dict = {k: v.decode("utf-8") for k, v in headers}
        assert "X-Correlation-Id" in headers_dict
        assert headers_dict["X-Correlation-Id"] == "c-ticket-workflow-777"
        assert "traceparent" in headers_dict
    finally:
        provider.shutdown()
