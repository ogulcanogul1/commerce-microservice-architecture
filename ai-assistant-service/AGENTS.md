# AI Assistant Service - Mimari ve Mühendislik Kuralları (AGENTS.md)

## 1. Servis Rolü ve Sorumlulukları
- **Servis Adı:** `ai-assistant-service`
- **Teknoloji Yığını:** Python 3.12+, FastAPI, Astral `uv`, OpenTelemetry, Redis, `aiokafka`, `py-eureka-client`.
- **Varsayılan Port:** `8089` (Debezium Kafka Connect `8088` ile çakışmaması için).
- **Veritabanı Kuralı (Non-Negotiable):** Bu servis **KESİNLİKLE** diğer mikroservislerin PostgreSQL veritabanlarına doğrudan bağlanamaz. Tüm veri okuma/yazma işlemleri HTTP (`order-service`, `product-service`, `shipping-service`, `inventory-service`) ve Apache Kafka (`support.ticket.created`) üzerinden gerçekleştirilir.

## 2. Güvenlik ve İzleme Kuralları
- **Gateway Bypass Koruması:** `/actuator/**` ve `/docs` dışındaki tüm uç noktalar `X-Gateway-Secret` başlığını doğrular.
- **IDOR Koruması:** Ajan tool fonksiyonları müşteri kimliğini kullanıcı prompt'undan değil, API Gateway'in doğruladığı `X-User-Id` başlığından (`RequestContext`) alır. `customer_id` asla araç parametre şemasına eklenemez (`extra="forbid"`).
- **PII Maskeleme:** Kredi kartı, TCKN gibi hassas veriler dış LLM sağlayıcılarına gönderilmeden önce maskelenir. Adres ve alıcı adı gibi PII alanları downstream modellerden LLM context'ine aktarılmaz.
- **Standart Olay Zarfı:** Kafka'ya basılan tüm olaylar (`support.ticket.created`) platformun standart `EventEnvelope` şemasına (`eventId`, `eventType`, `aggregateId`, `aggregateType`, `timestamp`, `version`, `correlationId`, `causationId`, `payload`) uymak zorundadır.

## 3. Müşteri Destek Ajanı Kuralları (Customer Support Agent)
- **Onaylı Aksiyon Modeli (Human-in-the-Loop):** Model doğrudan veritabanında veya sipariş üzerinde değişiklik (iptal vb.) yapamaz. Yalnızca `PendingAction` önerisi oluşturabilir. İşlem yalnızca kullanıcının `POST /agent/actions/{action_id}/confirm` çağrısıyla gerçekleşir.
- **Sahiplik Doğrulaması (Kargo):** Kargo sorguları asla doğrudan kargo takip numarası ile yapılamaz; önce sipariş sahipliği `order-service` üzerinden doğrulanır, ardından sipariş ID ile kargo servisi çağrılır.
- **Terminal Politika Kuralı:** İade, kargo, garanti gibi şirket politikası sorularında `search_policy` çağrıldığında RAG cevabı modele özetletilmeden atıflarıyla birlikte doğrudan kullanıcıya döndürülür.
- **Grounding Kuralı:** Asistan, araç çağırmadan sayısal bilgi veremez veya araç çıktısında yer almayan uydurma rakamlar üretemez. İhlal durumunda 1 düzeltme hakkı tanınır, aksi halde güvenli fallback mesajı dönülür.
- **Log Hijyeni:** Loglarda ham `user_id` (yerine SHA-256 hash'i kullanılır), serbest kullanıcı mesajı ve sipariş tutarları asla yer alamaz.
