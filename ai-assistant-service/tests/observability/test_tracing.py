"""OpenTelemetry Tracing Kurulumu Birim Testleri.

Bu testler, OpenTelemetry TracerProvider kurulumunun doğruluğunu test eder.
UYARI: Global OTel durumunu kirletmemek adına testlerde asla `trace.set_tracer_provider()`
çağrısı içeren `setup_tracing(app)` fonksiyonu OTEL_ENABLED=True ile test edilmez.
Yerel provider üretimi `build_tracer_provider` üzerinden izole olarak test edilir.
"""

from fastapi import FastAPI
from opentelemetry import trace
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from app.core.config import settings
from app.observability.tracing import (
    build_tracer_provider,
    setup_tracing,
    shutdown_tracing,
)


def test_build_tracer_provider_resource_attributes_and_span_creation():
    """İzole TracerProvider nesnesinin doğru servis ve ortam meta verilerine (Resource)

    sahip olduğunu ve span oluşturabildiğini doğrular.
    """
    # 1. Hafıza-içi dışa aktarıcı (InMemorySpanExporter) ve işlemci hazırla
    memory_exporter = InMemorySpanExporter()
    processor = SimpleSpanProcessor(memory_exporter)

    # 2. Global state'e dokunmadan yerel provider oluştur
    provider = build_tracer_provider(processor)

    # 3. Resource üzerindeki servis adı ve ortam etiketlerini kontrol et
    resource_attrs = provider.resource.attributes
    assert resource_attrs["service.name"] == settings.SERVICE_NAME
    assert resource_attrs["deployment.environment"] == settings.ENVIRONMENT

    # 4. Bu provider üzerinden izole bir span açıp kapat
    tracer = provider.get_tracer("test-tracer")
    with tracer.start_as_current_span("test-operation") as span:
        span.set_attribute("custom.key", "custom-value")

    # 5. Span'in belleğe başarıyla yazıldığını doğrula
    spans = memory_exporter.get_finished_spans()
    assert len(spans) == 1
    assert spans[0].name == "test-operation"
    assert spans[0].attributes["custom.key"] == "custom-value"

    # 6. Provider temizliği
    provider.shutdown()


def test_setup_tracing_disabled_returns_none(monkeypatch):
    """OTEL_ENABLED=False iken setup_tracing'in None döndüğünü ve hiçbir enstrümantasyon

    yapmadığını doğrular.
    """
    monkeypatch.setattr(settings, "OTEL_ENABLED", False)

    fake_app = FastAPI()
    result = setup_tracing(fake_app)

    # Tracing kapalı olduğu için None dönmeli
    assert result is None


def test_shutdown_tracing_graceful():
    """shutdown_tracing fonksiyonunun None veya geçerli bir provider ile güvenle

    hata fırlatmadan çalıştığını doğrular.
    """
    # None verilirse hata fırlatmamalı
    shutdown_tracing(None)

    # Geçerli bir sağlayıcı verilirse shutdown() çağrılmalı ve kapanmalı
    memory_exporter = InMemorySpanExporter()
    provider = build_tracer_provider(SimpleSpanProcessor(memory_exporter))
    shutdown_tracing(provider)
