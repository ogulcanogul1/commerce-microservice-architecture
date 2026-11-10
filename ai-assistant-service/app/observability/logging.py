"""Tek satır JSON loglama, trace/correlation enjeksiyonu ve PII maskeleme modülü.

Bu modül, mikroservis loglama altyapısını kurumsal dağıtık sistem standartlarına kavuşturur:
1. Grafana Loki uyumluluğu için her log kaydını tek satır (single-line) JSON formatına çevirir.
2. Java mikroservisleriyle (order-service, shipping-service) ortak log korelasyonu sağlamak için
   her satıra 'traceId', 'spanId' ve 'correlationId' alanlarını otomatik ekler.
3. Formatter seviyesinde PII (Kişisel Veri) maskelemesi yaparak TCKN, kredi kartı, IBAN,
   telefon ve e-posta bilgilerinin loglara düz metin olarak sızmasını kesin olarak engeller.
4. Python root logger'ına stdout StreamHandler bağlayarak logların üretimde kaybolmasını (L1) çözer.
5. Uvicorn erişim loglarındaki periyodik sağlık ve metrik kontrollerini filtreler.
"""

from datetime import datetime, timezone
import json
import logging
import sys

from opentelemetry import trace

from app.core.config import settings
from app.core.pii import mask_pii
from app.observability.context import correlation_id_var

# Yerel geliştirme ortamında (LOG_FORMAT=text) terminalde okunabilir metin formatı
_TEXT_FORMAT = (
    "%(asctime)s %(levelname)5s [%(service)s,%(traceId)s,%(spanId)s,%(correlationId)s] %(name)s : %(message)s"
)

# Sağlık kontrolü ve metrik toplama (scrape) yolları yüksek frekansla çağrıldığı için
# uvicorn.access loglarında gürültü yaratmaması adına filtrelenir.
_QUIET_ACCESS_PATHS = ("/health", "/actuator/prometheus", "/actuator/health")


class TraceContextFilter(logging.Filter):
    """Her log kaydına aktif span'in traceId/spanId'sini ve correlationId'yi enjekte eden filtre.
    
    Bu filtre sayesinde geliştirici log satırına hiçbir ekstra parametre geçmese bile
    (`logger.info("Sipariş işlendi")`), arka plandaki aktif OTel span'i ve ContextVar okunarak
    log kaydına iliştirilir.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        # 1. Aktif OpenTelemetry span bağlamını (context) oku
        ctx = trace.get_current_span().get_span_context()
        
        # Span geçerliyse W3C standardına uygun hex formatında yaz (traceId: 32 karakter, spanId: 16 karakter)
        record.traceId = format(ctx.trace_id, "032x") if ctx.is_valid else ""
        record.spanId = format(ctx.span_id, "016x") if ctx.is_valid else ""
        
        # 2. Adım 3'te ContextVar olarak sakladığımız aktif istek Correlation ID'sini oku
        record.correlationId = correlation_id_var.get() or ""
        
        # 3. Servis adını ekle (Grafana Loki ve Tempo eşleştirmesi için)
        record.service = settings.SERVICE_NAME
        return True


class AccessLogNoiseFilter(logging.Filter):
    """Uvicorn access loglarından düzenli probe ve scrape yollarını süzen filtre.
    
    Örnek: Her 5 saniyede bir gelen GET /actuator/prometheus istekleri log dosyalarını
    şişirmesin diye elenir; ancak /agent/chat veya /rag/search gibi iş istekleri loglanır.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        return not any(path in message for path in _QUIET_ACCESS_PATHS)


class JsonLogFormatter(logging.Formatter):
    """Loki için tek satır JSON üreten ve PII maskeleyen özel formatlayıcı.
    
    Java mikroservislerindeki MDC (Mapped Diagnostic Context) anahtarlarıyla tam uyumludur:
    - traceId
    - spanId
    - correlationId
    """

    def format(self, record: logging.LogRecord) -> str:
        # L3 Koruması: Mesaj yazılmadan hemen önce mask_pii ile hassas verilerden temizlenir
        raw_message = record.getMessage()
        masked_message, _ = mask_pii(raw_message)

        # Temel JSON yükü (Payload)
        payload: dict[str, object] = {
            "timestamp": datetime.fromtimestamp(record.created, timezone.utc).isoformat(timespec="milliseconds"),
            "level": record.levelname.lower(),
            "service": getattr(record, "service", settings.SERVICE_NAME),
            "logger": record.name,
            "message": masked_message,
        }

        # Dağıtık izleme kimlikleri varsa ekle (Loki'de `| json | correlationId="..."` sorgusu için)
        for key in ("traceId", "spanId", "correlationId"):
            value = getattr(record, key, "")
            if value:
                payload[key] = value

        # L2 Koruması: Hata (exception) durumunda stack trace'i tek satırlık string alanına al
        # Böylece Loki'de 30 satırlık bir hata 30 ayrı kayıt yerine TEK bir log kaydı olur.
        if record.exc_info:
            formatted_exc = self.formatException(record.exc_info)
            # Stack trace içinde de fonksiyon argümanlarından PII sızabileceği için onu da maskele
            masked_exc, _ = mask_pii(formatted_exc)
            payload["stack_trace"] = masked_exc

        # Tek satır JSON dizesine dönüştür (ensure_ascii=False ile Türkçe karakterler bozulmaz)
        return json.dumps(payload, ensure_ascii=False)


def configure_logging() -> None:
    """Uygulama genelinde loglama altyapısını yapılandırır.
    
    Çözülen Problemler:
    1. Root logger'a stdout StreamHandler bağlayarak L1 (sessiz log kaybı) sorununu çözer.
    2. Ayara göre (LOG_FORMAT=json) JSON formatlayıcıyı devreye alır.
    3. TraceContextFilter ile otomatik trace ve correlation ID enjeksiyonu sağlar.
    4. Uvicorn logger'larının bağımsız handler'larını temizleyip root logger'a yönlendirir,
       böylece tüm web sunucusu logları da aynı standart formatta çıkar.
    """
    # 1. Standart çıktı (stdout) işleyicisi oluştur
    handler = logging.StreamHandler(sys.stdout)
    
    # 2. Trace ve Correlation ID zenginleştirici filtreyi ekle
    handler.addFilter(TraceContextFilter())
    
    # 3. Ortam ayarına göre formatlayıcıyı bağla
    if settings.LOG_FORMAT == "json":
        handler.setFormatter(JsonLogFormatter())
    else:
        handler.setFormatter(logging.Formatter(_TEXT_FORMAT))

    # 4. Root logger'ı yapılandır
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(logging.INFO)

    # 5. Uvicorn logger'larını root logger'a yönlendir (propagate = True)
    # Kendi handler'larını kaldırıyoruz ki aynı satır konsola iki kez veya farklı formatta basılmasın
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        uv_logger = logging.getLogger(name)
        uv_logger.handlers = []
        uv_logger.propagate = True

    # 6. Erişim loglarına gürültü filtresini uygula
    logging.getLogger("uvicorn.access").addFilter(AccessLogNoiseFilter())
