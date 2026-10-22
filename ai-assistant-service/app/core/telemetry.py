import logging

from fastapi import FastAPI
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from app.core.config import settings

logger = logging.getLogger(__name__)

_httpx_instrumented = False


def setup_telemetry(app: FastAPI) -> None:
    """
    Configures OpenTelemetry W3C TraceContext propagation and OTLP HTTP export to Grafana Tempo.
    Ensures seamless trace continuity between Java Spring Boot services and Python FastAPI.
    """
    global _httpx_instrumented

    resource = Resource.create(
        {
            "service.name": settings.SERVICE_NAME,
            "service.version": "0.1.0",
            "deployment.environment": settings.ENVIRONMENT,
        }
    )
    provider = TracerProvider(resource=resource)

    if settings.OTEL_ENABLED and settings.OTEL_EXPORTER_OTLP_ENDPOINT:
        exporter = OTLPSpanExporter(endpoint=settings.OTEL_EXPORTER_OTLP_ENDPOINT)
        provider.add_span_processor(BatchSpanProcessor(exporter))
        logger.info(
            "OpenTelemetry OTLP exporter initialized for endpoint: %s",
            settings.OTEL_EXPORTER_OTLP_ENDPOINT,
        )

    trace.set_tracer_provider(provider)
    FastAPIInstrumentor.instrument_app(app, tracer_provider=provider)

    if not _httpx_instrumented:
        HTTPXClientInstrumentor().instrument()
        _httpx_instrumented = True
