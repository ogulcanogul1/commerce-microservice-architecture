"""OpenTelemetry Dağıtık İzleme (Tracing) Kurulum Modülü.

Bu modül, mikroservisin OpenTelemetry (OTel) tabanlı trace altyapısını kurar:
1. API Gateway'den gelen 'traceparent' HTTP başlığını yakalayarak var olan trace zincirine katılır.
2. Servis içinden httpx ile yapılan downstream çağrılara (order-service, shipping-service)
   'traceparent' başlığını otomatik olarak enjekte eder.
3. Üretilen span verilerini HTTP OTLP protokolü üzerinden Tempo sunucusuna aktarır.

Not: Metrikler (Prometheus) ve loglar (stdout/Promtail) ayrı kanallardan iletildiği için
bu modül YALNIZCA trace (iz) verilerini yönetir.
"""

from fastapi import FastAPI
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, SpanProcessor

from app.core.config import settings

# Sistem probe'ları (sağlık kontrolleri) ve Prometheus metrik toplama (scrape) istekleri
# sürekli ve yüksek frekansta (örn. her 5-10 saniyede bir) çalışır.
# Bu istekler gerçek kullanıcı akışıyla ilgisiz olduğundan Tempo'da gürültü yaratmaması
# ve depolama alanını gereksiz şişirmemesi için trace kapsamı dışında bırakılır.
_EXCLUDED_URLS = "/health,/actuator/prometheus,/actuator/health"


def build_tracer_provider(*extra_processors: SpanProcessor) -> TracerProvider:
    """İzole ve test edilebilir bir TracerProvider örneği oluşturur.
    
    Neden ayrı bir fonksiyon?
    Birim testlerde OpenTelemetry'nin global tekil (singleton) durumunu değiştirmeden
    hafıza-içi (InMemorySpanExporter) izole testler yapabilmek için bu fabrika fonksiyonu kullanılır.
    
    Args:
        *extra_processors: Sağlayıcıya eklenecek span işleyicileri (BatchSpanProcessor, InMemory vb.)
        
    Returns:
        Yapılandırılmış TracerProvider nesnesi.
    """
    # Resource: Bu servis tarafından üretilen her span'e otomatik iliştirilecek kimlik meta verileri.
    # Tempo ve Grafana'da izleri servise ve ortama göre filtrelemek için kullanılır.
    resource = Resource.create(
        {
            "service.name": settings.SERVICE_NAME,
            "deployment.environment": settings.ENVIRONMENT,
        }
    )
    
    # Varsayılan örnekleyici: ParentBased(ALWAYS_ON).
    # Yani istek zinciri gateway'den geliyorsa gateway'in verdiği örnekleme (sampled) kararına uyar.
    # Doğrudan gelen yeni isteklerde ise varsayılan olarak trace başlatır.
    provider = TracerProvider(resource=resource)
    
    # İlgili span işlemcilerini sağlayıcıya kaydet
    for processor in extra_processors:
        provider.add_span_processor(processor)
        
    return provider


def setup_tracing(app: FastAPI) -> TracerProvider | None:
    """Uygulama açılışında OpenTelemetry tracing'i başlatır ve enstrümante eder.
    
    OTEL_ENABLED ayarı False ise (örneğin yerel birim testlerde veya tracing istenmeyen ortamlarda)
    hiçbir işlem yapmaz ve None döner.
    
    Args:
        app: Enstrümante edilecek FastAPI uygulama örneği.
        
    Returns:
        Aktif TracerProvider nesnesi veya kapalıysa None.
    """
    if not settings.OTEL_ENABLED:
        return None

    # DİKKAT (Kritik Mimari Detay):
    # 'endpoint' argümanını OTLPSpanExporter'a açıkça (explicit) geçiyoruz.
    # Eğer ortam değişkeninden otomatik okumaya bırakılsaydı, SDK endpoint sonuna
    # varsayılan olarak bir kez daha '/v1/traces' ekleyecek ve çift path oluşacaktı
    # (örn: http://tempo:4318/v1/traces/v1/traces -> 404 Not Found ve sessiz iz kaybı).
    exporter = OTLPSpanExporter(endpoint=settings.OTEL_EXPORTER_OTLP_ENDPOINT)
    
    # BatchSpanProcessor: Üretilen her span için ayrı ayrı HTTP isteği atmak yerine,
    # span'leri arka planda küçük gruplar halinde tamponlayıp topluca Tempo'ya gönderir.
    # Bu sayede asıl API çağrısının yanıt süresine gecikme (latency) eklemez.
    batch_processor = BatchSpanProcessor(exporter)
    provider = build_tracer_provider(batch_processor)
    
    # OTel global tracer provider olarak bu sağlayıcıyı kaydet
    trace.set_tracer_provider(provider)
    
    # 1. FastAPI Enstrümantasyonu: Gelen HTTP isteklerindeki 'traceparent' başlığını okur,
    # ilgili route için otomatik bir server span oluşturur ve bağlamı (context) başlatır.
    FastAPIInstrumentor.instrument_app(app, excluded_urls=_EXCLUDED_URLS)
    
    # 2. HTTPX Enstrümantasyonu: Kod içerisinden OrderClient veya ShippingClient ile
    # diğer mikroservislere HTTP çağrısı yapıldığında, aktif 'traceparent' başlığını
    # giden isteğin HTTP başlıklarına otomatik olarak enjekte eder (W3C Trace Context).
    HTTPXClientInstrumentor().instrument()
    
    return provider


def shutdown_tracing(provider: TracerProvider | None) -> None:
    """Uygulama kapanırken (graceful shutdown) tamponda bekleyen span'leri dışa aktarır.
    
    BatchSpanProcessor belleğinde gönderilmeyi bekleyen span'ler olabilir.
    Servis SIGTERM aldığında provider kapatılarak bu span'lerin Tempo'ya flush edilmesi
    sağlanır, böylece son isteklerin izleri kaybolmaz.
    
    Args:
        provider: setup_tracing tarafından döndürülen sağlayıcı örneği.
    """
    if provider is not None:
        provider.shutdown()
