"""Kafka mesaj başlıkları (Headers) üzerinden trace context ve correlation ID aktarım modülü.

Bu modül, mikroservisler arası asenkron olay iletişiminde (Apache Kafka) gözlemlenebilirlik
zincirinin kopmamasını sağlar.

Neden Gereklidir?
- HTTP çağrılarında OpenTelemetry kütüphaneleri W3C Trace Context (traceparent) başlıklarını
  otomatik olarak aktarabilirken, aiokafka gibi asenkron mesajlaşma kütüphanelerinde bu aktarım
  otomatik yapılmaz.
- Bu modül, o anki aktif OpenTelemetry span'inden 'traceparent' ve 'tracestate' başlıklarını çeker,
  ayrıca Java mikroservisleriyle (notification-service, OutboxPoller) uyumlu şekilde
  'X-Correlation-Id' başlığını ekleyerek Kafka üreticisine (producer) teslim eder.
"""

from opentelemetry import propagate

# Yalnızca standart W3C trace context başlıkları taşınır.
# Güvenlik ve bant genişliği hijyeni: Baggage başlığı bilerek taşınmaz.
_TRACE_HEADERS = ("traceparent", "tracestate")


def build_kafka_headers(correlation_id: str | None) -> list[tuple[str, bytes]]:
    """O anki aktif span'den traceparent başlığını üretir ve correlation ID ile birleştirir.
    
    Args:
        correlation_id: Olayın tetiklenmesine neden olan iş akışının Correlation ID'si.
        
    Returns:
        aiokafka'nın `send_and_wait` metodunun beklediği `list[tuple[str, bytes]]` formatında
        Kafka mesaj başlıkları listesi.
    """
    carrier: dict[str, str] = {}
    
    # 1. OpenTelemetry Context API: Aktif span'i carrier sözlüğüne W3C formatında enjekte et
    # Eğer aktif bir span yoksa carrier boş sözlük olarak kalır.
    propagate.inject(carrier)

    # 2. Yalnızca traceparent ve tracestate başlıklarını UTF-8 bayt dizisine dönüştürerek al
    headers: list[tuple[str, bytes]] = [
        (key, value.encode("utf-8"))
        for key, value in carrier.items()
        if key in _TRACE_HEADERS
    ]

    # 3. Correlation ID varsa Java servislerinin (notification-service vb.) beklediği
    # 'X-Correlation-Id' başlığıyla ekle
    if correlation_id:
        headers.append(("X-Correlation-Id", correlation_id.encode("utf-8")))

    return headers
