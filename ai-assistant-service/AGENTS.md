# AI Assistant Service - Mimari ve Mühendislik Kuralları (AGENTS.md)

## 1. Servis Rolü ve Sorumlulukları
- **Servis Adı:** `ai-assistant-service`
- **Teknoloji Yığını:** Python 3.12, FastAPI, Paket Yöneticisi: **Astral `uv`**, OpenTelemetry, Redis, `aiokafka`, `py-eureka-client`.
- **Varsayılan Port:** `8089` (Debezium Kafka Connect `8088` ile çakışmaması için).
- **Veritabanı Kuralı (Non-Negotiable):** Bu servis **KESİNLİKLE** diğer mikroservislerin PostgreSQL veritabanlarına doğrudan bağlanamaz. Tüm veri okuma/yazma işlemleri HTTP (`order-service`, `product-service`, `shipping-service`, `inventory-service`) ve Apache Kafka (`support.ticket.created`) üzerinden gerçekleştirilir.

## 2. Güvenlik ve İzleme Kuralları
- **Gateway Bypass Koruması:** `/actuator/**` ve `/docs` dışındaki tüm uç noktalar `X-Gateway-Secret` başlığını doğrular.
- **IDOR Koruması:** Ajan tool fonksiyonları müşteri kimliğini kullanıcı prompt'undan değil, API Gateway'in doğruladığı `X-User-Id` başlığından (`RequestContext`) alır.
- **PII Maskeleme:** Kredi kartı, TCKN gibi hassas veriler dış LLM sağlayıcılarına gönderilmeden önce maskelenir.
- **Standart Olay Zarfı:** Kafka'ya basılan tüm olaylar (`support.ticket.created`) platformun standart `EventEnvelope` şemasına (`eventId`, `eventType`, `aggregateId`, `aggregateType`, `timestamp`, `version`, `correlationId`, `causationId`, `payload`) uymak zorundadır.
