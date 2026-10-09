# Commerce Platform - Dağıtık ve Olay Güdümlü Mikroservis Mimarisi

[![Java](https://img.shields.io/badge/Java-21%20LTS-orange.svg?style=flat&logo=openjdk)](https://www.oracle.com/java/)
[![Spring Boot](https://img.shields.io/badge/Spring%20Boot-4.1.x-brightgreen.svg?style=flat&logo=springboot)](https://spring.io/projects/spring-boot)
[![Spring Cloud](https://img.shields.io/badge/Spring%20Cloud-2025.x-blue.svg?style=flat&logo=spring)](https://spring.io/projects/spring-cloud)
[![Apache Kafka](https://img.shields.io/badge/Apache%20Kafka-KRaft-red.svg?style=flat&logo=apachekafka)](https://kafka.apache.org/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-blue.svg?style=flat&logo=postgresql)](https://www.postgresql.org/)
[![Redis](https://img.shields.io/badge/Redis-7-darkred.svg?style=flat&logo=redis)](https://redis.io/)
[![Docker](https://img.shields.io/badge/Docker-Compose-2496ED.svg?style=flat&logo=docker)](https://www.docker.com/)

> **Commerce Platform**, basit CRUD operasyonları yerine gerçek dünya dağıtık sistem (distributed systems) zorlukları etrafında tasarlanmış; üretime hazır (production-grade), olay güdümlü (event-driven) ve bulut tabanlı bir e-ticaret platformudur.

---

## 1. Proje Vizyonu ve Temel Mühendislik İlkesi

Bu proje; teknolojileri popüler oldukları için eklemek yerine şu temel mühendislik sorusuna yanıt vermek amacıyla inşa edilmiştir:

> **"Hangi dağıtık sistem problemini çözüyorum ve bunu çözmek için hangi teknoloji/tasarım deseni uygundur?"**

| Dağıtık Sistem Problemi | Çözüm Deseni / Teknoloji |
| :--- | :--- |
| **Dağıtık İşlemler (Distributed Transactions)** | Orkestre Edilmiş Saga Deseni (`order-service`) |
| **Güvenilir Olay Yayınlama (Dual-Write Problemi)** | Transactional Outbox Deseni + Debezium / CDC Poller |
| **Veritabanı - Olay Senkronizasyonu** | Debezium / Kafka Connect ile Change Data Capture (CDC) |
| **Yinelenen Mesaj İşleme (At-least-once Delivery)** | Kesin Tüketici Idempotency (`processed_events` tekilleştirmesi) |
| **Finansal İsteklerin Çift İşlenmesi** | `Idempotency-Key` HTTP Başlığı ve Doğrulama Tablosu |
| **Bağımsız Okuma/Yazma Ölçekleme** | CQRS (Command Query Responsibility Segregation) |
| **Yüksek Okuma Performansı (Ürün Kataloğu)** | Redis Cache-Aside Deseni (Sıkı TTL ve Eviction) |
| **Aşırı Satış Riski (Overselling / Race Conditions)** | JPA `@Version` İyimser Kilitleme (Optimistic Locking) |
| **Zehirli Mesajlar ve Kalıcı Hatalar** | Üstel Geri Çekilme (Exponential Backoff) + Dead Letter Queue (`.DLT`) |
| **Geçici Servis Kesintileri** | Devre Kesici (Resilience4j Circuit Breaker) + Zarif Geri Dönüşler (Fallback) |
| **Dağıtık İzleme ve Bağlam Taşıma** | OpenTelemetry + `X-Correlation-Id` ve `X-Causation-Id` başlıkları |
| **Trafik Şekillendirme ve Hız Limiti** | Spring Cloud Gateway + Redis Token Bucket Rate Limiter |

---

## 2. Yüksek Seviyeli Sistem Mimarisi

> **Önemli Mimari Ayrım (Orchestration vs Choreography)**:
> Sistemde olaylar alt servisler tarafından aynı anda rastgele veya paralel olarak dinlenmez (**Koreografi değil**).
> **`order-service` bir Orkestra Şefidir (Saga Orchestrator)**. Stok, Ödeme ve Kargo adımlarını Kafka üzerinden **sıra sıra (sequential)** ve çift yönlü olarak yönetir.

```text
                                  ┌─────────────────┐
                                  │     İstemci     │
                                  └────────┬────────┘
                                           │ HTTP / JSON
                                           ▼
                              ┌────────────────────────┐
                              │    Spring Cloud        │
                              │       Gateway          │
                              │       (Port: 8080)     │
                              │ Auth / Rate Limit      │
                              │ Routing / Circuit Brk  │
                              └────────────┬───────────┘
                                           │
             ┌─────────────────────────────┼─────────────────────────────┐
             │                             │                             │
             ▼                             ▼                             ▼
     ┌───────────────┐             ┌───────────────┐             ┌───────────────┐
     │ Product       │             │ Customer      │             │ Order Service │
     │ Service(8081) │             │ Service(8086) │             │ (Port: 8082)  │
     │ Redis Önbellek│             │ Profil / Adres│             │ [Saga Şefi]   │
     └───────────────┘             └───────────────┘             └───────┬───────┘
                                                                         │
                  ┌──────────────────────────────────────────────────────┴──────────────────────┐
                  │                 Apache Kafka Event Backbone                                 │
                  │   Adım adım (sequential) çift yönlü orkestrasyon mesajlaşma akışı           │
                  └───┬─────────────▲─────────────┬─────────────▲─────────────┬─────────────▲───┘
                      │ (1)         │ (2)         │ (3)         │ (4)         │ (5)         │ (6)
                      │ Stok        │ Stok        │ Ödeme       │ Ödeme       │ Kargo       │ Kargo
                      │ Emri        │ Yanıtı      │ Emri        │ Yanıtı      │ Emri        │ Yanıtı
                      ▼             │             ▼             │             ▼             │
                ┌───────────────────┴─┐     ┌───────────────────┴─┐     ┌───────────────────┴─┐
                │  Inventory Service  │     │   Payment Service   │     │  Shipping Service   │
                │     (Port: 8084)    │     │     (Port: 8083)    │     │     (Port: 8085)    │
                │  Stok Rezervasyonu  │     │  Tahsilat & Prov.   │     │  Kargo & Takip No   │
                └─────────────────────┘     └─────────────────────┘     └─────────────────────┘
                                                                                   │
                                (Sipariş Onaylandı / İptal Olayı)                 │ (7)
                                 orders.confirmed / orders.cancelled               │
                                                                                   ▼
                                                                        ┌─────────────────────┐
                                                                        │Notification Service │
                                                                        │     (Port: 8087)    │
                                                                        │  E-posta / SMS Gönd.│
                                                                        └─────────────────────┘
```

---

## 3. Servis Kataloğu, Portlar ve Veritabanları

> **Temel Mimari Kural**: Servis Başına Veritabanı (Database-Per-Service). Mikroservisler birbirlerinin veritabanlarına asla doğrudan bağlanamaz, çapraz SQL sorgusu atamaz. Tüm veri senkronizasyonu Kafka üzerinden yürütülür.

| Servis Adı | Dizin | Port | Veritabanı | Sorumluluk |
| :--- | :--- | :--- | :--- | :--- |
| **API Gateway** | `api-gateway` | `8080` | Redis (6379) | Ters proxy, JWT doğrulama, Redis hız limiti, Resilience4j devre kesici, Correlation-ID enjeksiyonu |
| **Product Service** | `product-service` | `8081` | `product_db` / Redis | Ürün kataloğu, kategoriler, fiyatlandırma, Redis Cache-Aside önbelleği |
| **Order Service** | `order-service` | `8082` | `order_db` | Sipariş yaşam döngüsü, Saga Orkestratörü, Transactional Outbox |
| **Payment Service** | `payment-service` | `8083` | `payment_db` | Ödeme provizyonu, tahsilat, iade, `Idempotency-Key` denetimi |
| **Inventory Service** | `inventory-service` | `8084` | `inventory_db` | Stok takibi, rezervasyon, TTL ile süre aşımı, `@Version` iyimser kilitleme |
| **Shipping Service** | `shipping-service` | `8085` | `shipping_db` | Kargo kaydı oluşturma, takip numarası üretimi, teslimat simülasyonu |
| **Customer Service** | `customer-service` | `8086` | `customer_db` | Müşteri profili, kayıtlı adresler, kullanıcı tercihleri |
| **Notification Service** | `notification-service` | `8087` | `notification_db` | Kafka olay dinleyicisi (Pure Consumer), E-posta / SMS bildirim simülatörü |

---

## 4. Sipariş Saga Orkestrasyon Akışı (Saga Pattern)

Sipariş süreci **merkezi durum makinesi (State Machine)** ile `order-service` tarafından orkestre edilir. Her adım bir önceki adımın başarılı Kafka olayına istinaden tetiklenir:

```text
       [Müşteri Sipariş Talebi]
                  │
                  ▼
          ┌───────────────┐
          │  Sipariş Aç   │ ──(1. orders.created)────► [Inventory Service]
          │   (PENDING)   │                                   │
          └───────────────┘                                   ▼
                  ▲                                   (Stok Rezerve Et)
                  │                                           │
                  │ ◄──(2. inventory.reserved)────────────────┘
                  ▼
          ┌───────────────┐
          │ Stok Rezerve  │ ──(3. payments.process)──► [Payment Service]
          │(INV_RESERVED) │                                   │
          └───────────────┘                                   ▼
                  ▲                                   (Ödemeyi Tahsil Et)
                  │                                           │
                  │ ◄──(4. payments.authorized)───────────────┘
                  ▼
          ┌───────────────┐
          │ Ödeme Alındı  │ ──(5. shipments.create)──► [Shipping Service]
          │  (PAY_AUTH)   │                                   │
          └───────────────┘                                   ▼
                  ▲                                   (Kargo Takip No Aç)
                  │                                           │
                  │ ◄──(6. shipments.created)─────────────────┘
                  ▼
          ┌───────────────┐
          │   CONFIRMED   │ ──(7. orders.confirmed)──► [Notification Service]
          │ (Sipariş Tam) │                            (E-posta / SMS Gönderimi)
          └───────────────┘
```

### Telafi İşlemleri (Compensating Transactions - Geri Alma Akışı):
Hata anında yapılan işlemler geriye doğru adım adım telafi edilir:
- **1. Adım Hatası (Stok Yoksa - `inventory.failed`)**: 
  - Sipariş doğrudan `INVENTORY_FAILED` ➔ `CANCELLED` durumuna geçer. 
  - Henüz ödeme alınmadığı ve kargo açılmadığı için geri alınacak başka bir işlem yoktur.
- **2. Adım Hatası (Ödeme Başarısızsa - `payments.failed`)**: 
  - Sipariş `PAYMENT_FAILED` ➔ `CANCELLED` durumuna geçer. 
  - **Telafi**: Rezerve edilen stoğu rafa geri koymak için `inventory.released` olayı tetiklenir.
- **3. Adım Hatası (Kargo Açılamazsa - `shipments.failed`)**: 
  - Sipariş `SHIPPING_FAILED` ➔ `CANCELLED` durumuna geçer. 
  - **1. Telafi**: Çekilen para müşteriye iade edilir (`payments.refunded`).
  - **2. Telafi**: Rezerve edilen stok serbest bırakılır (`inventory.released`).

---

## 5. Standart Olay Zarfı (Unified Event Envelope)

Kafka üzerinden iletilen tüm mesajlar ortak JSON zarf şemasına uyar:

```json
{
  "eventId": "c73a7924-4f40-4f51-b847-f404e5443fa7",
  "eventType": "OrderCreated",
  "aggregateId": "ORD-12345",
  "aggregateType": "Order",
  "timestamp": "2026-10-03T19:30:00Z",
  "version": 1,
  "correlationId": "9d1b1160-5f25-4c07-b2fa-5b12da61bb81",
  "causationId": "48b61c92-b67e-4d43-982f-2d7c66a87c12",
  "payload": {
    "orderId": "ORD-12345",
    "customerId": "CUST-987",
    "totalAmount": 1500.00,
    "currency": "TRY",
    "items": [
      { "sku": "SKU-LAPTOP-01", "quantity": 1, "unitPrice": 1500.00 }
    ]
  }
}
```

---

## 6. Altyapı ve Yerel Kurulum

Platform; bağımsız çalışan PostgreSQL veritabanları, Redis, Apache Kafka (KRaft) ve Kafka UI bileşenlerini içeren bir Docker Compose mimarisine sahiptir.

### 6.1. Altyapı Konteynerlerini Başlatma
```powershell
# Docker konteynerlerini arka planda başlatın
docker compose up -d

# Konteyner durumlarını kontrol edin
docker compose ps
```

Başlatılan Servisler:
- **PostgreSQL 16**: `localhost:5432` (`postgres` / `postgrespassword`) - Her servis veritabanı (`order_db`, `payment_db`, vb.) otomatik oluşturulur.
- **Redis 7**: `localhost:6379`
- **Apache Kafka (KRaft)**: `localhost:9092`
- **Kafka UI**: `http://localhost:8090` (Mesajları ve topic'leri tarayıcıdan izleyebilirsiniz)
- **Prometheus**: `http://localhost:9090` (Mikroservis Actuator metriklerini toplar)
- **Grafana Tempo**: `localhost:3200` (HTTP: `4318`, gRPC: `4317` OTLP trace alıcıları)
- **Grafana Loki**: `http://localhost:3100` (Yapısal log kümeleme)
- **Grafana**: `http://localhost:3000` (`admin` / `admin`) - Önceden tanımlı gösterge panelleri (Dashboards)

### 6.2. Mikroservisleri Derleme ve Çalıştırma
Her servis kendi bağımsız Maven Wrapper'ına sahiptir:

```powershell
# Örnek: order-service'i derleyin ve çalıştırın
cd order-service
.\mvnw clean package -DskipTests
.\mvnw spring-boot:run
cd ..
```

---

## 7. Gözlemlenebilirlik, Dağıtık İzleme ve Loglama Mimarisi (LGTM Stack)

Platform; **Prometheus (Metrikler)**, **Tempo (Dağıtık İzler)**, **Loki (Loglar)** ve **Grafana (Görselleştirme)** bileşenlerinden oluşan kurumsal seviyede bir gözlemlenebilirlik mimarisine sahiptir.

```text
  [HTTP İstek] ──► [API Gateway] ──(X-Correlation-Id)──► [Order Service] ──► [PostgreSQL (Outbox)]
                         │                                       │
                    OpenTelemetry                           traceparent
                         │                                       ▼
                         ▼                              [Kafka Header Enjeksiyonu]
                 [Grafana Tempo] ◄────────────────────── [Kafka Tüketicisi Child Span]
                         ▲
                         │ (Derived Fields: TraceID ◄──► Logs)
                         ▼
                   [Grafana Loki] ◄── [Promtail] ◄── Container Console Logs
                         ▲
                         │
                 [Grafana Dashboard] ◄── [Prometheus] ◄── 8x /actuator/prometheus
```

### 7.1. Dağıtık Outbox Trace Kopması ve Çözümü (The Outbox Trace Gap)
- **Problem**: Geleneksel Spring Boot izlemesinde, HTTP isteği bittikten sonra veritabanındaki `outbox_events` tablosunu okuyan `@Scheduled` arka plan iş parçacığı ilk isteğin trace bağlamını kaybeder.
- **Çözüm**:
  1. `OutboxServiceImpl` aktif `Tracer` nesnesinden W3C `traceparent` (`00-{traceId}-{spanId}-01`), `correlationId` ve `causationId` bilgilerini yakalayarak `EventEnvelope` JSON payload'una kaydeder.
  2. `OutboxPoller` bu değerleri Kafka `ProducerRecord` başlıklarına (`traceparent`, `X-Correlation-Id`, `X-Causation-Id`) enjekte eder.
  3. Tüketici servislerde `factory.getContainerProperties().setObservationEnabled(true);` aktifleştirilerek gelen `traceparent` üzerinden otomatik **Child Span** başlatılır. Grafana Tempo'da tüm Saga adımları tek bir şelalede hiyerarşik olarak birleşir.

### 7.2. Kesintisiz MDC Korelasyon Zinciri (Mapped Diagnostic Context)
- **HTTP Filtresi**: Tüm downstream servislere eklenen `CorrelationIdFilter`, gelen `X-Correlation-Id` başlığını SLF4J `MDC`'ye yerleştirir ve cevap başlığında döndürür.
- **Kafka Tüketici Interceptor'ı**: `KafkaConsumerConfig` içerisindeki `RecordInterceptor`, Kafka'dan gelen mesaj işlenmeye başlarken `X-Correlation-Id` başlığını otomatik olarak consumer thread'inin MDC'sine koyar ve işlem sonunda temizler.
- **Log Formatı**: Konsol ve Loki logları `[%application,%traceId,%spanId,%correlationId]` deseniyle zenginleştirilir.

### 7.3. Grafana Çift Yönlü Gezinme (Trace-to-Logs & Logs-to-Trace)
- **Loki ➔ Tempo**: Loki log satırındaki `traceId` değeri `derivedFields` ile otomatik linke dönüştürülür; tıklandığında doğrudan Tempo'daki ilgili trace'i açar.
- **Tempo ➔ Loki**: Tempo'da herhangi bir span incelenirken `tracesToLogsV2` butonu ile o servisin o zaman dilimindeki ilgili logları tek tıkla filtrelenir.
- **NodeGraph**: Mikroservisler arası çağrı bağımlılık şeması Tempo üzerinde görsel olarak sunulur.

### 7.4. Önceden Yapılandırılmış Grafana Paneli (`commerce-overview.json`)
Grafana açıldığında (`http://localhost:3000`) hazır gelen panel şunları gerçek zamanlı gösterir:
- Mikroservis bazında HTTP istek hacmi (req/s), p95 gecikmeler ve 5xx hata oranları.
- **Saga Orkestrasyon Metrikleri**: Maksimum Saga tamamlanma süresi (`orders_saga_duration_seconds_max`), başarıyla biten ve telafi edilen/iptal olan siparişler.
- **Transactional Outbox & Idempotency**: Yayınlanan outbox olayları ve yinelenen/engellenen kopya Kafka mesajları (`events_duplicate_ignored_total`).
- Ödeme, stok rezervasyonu, kargo ve bildirim operasyonel sayaçları.

---

## 8. Hata Sınıflandırma ve Dayanıklılık Mimarisi (Resilience & Error Categorization)

Dağıtık sistemlerde her hataya körü körüne retry atmak bir felaket desenidir (**Retry Storm / Cascading Failure**). Platform genelinde tüm istisnalar iki temel köke ayrılmıştır:

```text
                                  ┌───────────────────────────┐
                                  │   Commerce Exception      │
                                  └─────────────┬─────────────┘
                                                │
                       ┌────────────────────────┴────────────────────────┐
                       ▼                                                 ▼
        [TransientException (Retryable)]                [BusinessRuleException (NonRetryable)]
        • Sunucu kilitlenmesi / Socket Timeout          • 4xx İstemci Hataları (400, 404, 409)
        • HTTP 503 / 504                                • Yetersiz Bakiye, Yetersiz Stok
        • DB Deadlock / OptimisticLockException         • Bozuk JSON (Poison Pill)
                       │                                                 │
                       ▼                                                 ▼
               【 RETRY PATTERN 】                               【 ASLA RETRY ATILMAZ! 】
          (Exponential Backoff + Jitter)                                 │
          (Resilience4j Circuit Breaker)            ┌────────────────────┼────────────────────┐
                                                    ▼                    ▼                    ▼
                                               [Fail-Fast]         [Saga Telafisi]      [Dead Letter]
                                             (ProblemDetails)       (Compensate)        (Kafka .DLT)
```

### 8.1. Sınıflandırma Standartları
- **`Retryable` Marker Interface**: Ağ parazitleri veya anlık kilitlenmeler gibi kendiliğinden düzelebilecek geçici altyapı hataları için kullanılır (`TransientException`).
- **`NonRetryable` Marker Interface**: İş kuralı ihlalleri, doğrulama hataları ve kalıcı problemler için kullanılır (`BusinessRuleException`).

### 8.2. Asenkron Kafka Hata Yönetimi (`DefaultErrorHandler`)
- Kafka dinleyicilerinde `errorHandler.addNotRetryableExceptions(BusinessRuleException.class, JsonProcessingException.class, IllegalArgumentException.class)` yapılandırılmıştır.
- Kalıcı bir hata veya bozuk JSON (Poison Pill) geldiğinde sistem 3 kez beklemeden **anında** mesajı `.DLT` kuyruğuna (ör. `orders.created.DLT`) aktarır; diğer sağlıklı mesajların işlenmesi asla tıkanmaz.

### 8.3. Senkron REST / HTTP Dayanıklılığı
- **4xx Hataları**: Asla retry edilmez, `GlobalExceptionHandler` üzerinden RFC 7807 `ProblemDetails` olarak fail-fast dönülür.
- **5xx / Timeout**: Yalnızca idempotent işlemler için Exponential Backoff ile retry uygulanır; hata oranı eşiği aştığında Resilience4j Circuit Breaker devreyi açarak servisi korur.

---

## 9. Kimlik Doğrulama ve Güvenlik Mimarisi (Authentication & Edge Security)

Platform genelinde mikroservisler arası güvenlik **Token-Based Edge Authentication & Token Relay** deseniyle sağlanır:

```text
                  ┌────────────────────────────────────────────────────────┐
                  │                 İSTEMCİ (Web / Mobil)                  │
                  └───────────────┬────────────────────────┬───────────────┘
                                  │                        │
         1. Normal / OAuth2 Login │                        │ 2. İstekler (Bearer JWT)
         (POST /api/v1/auth/...)  │                        │
                                  ▼                        ▼
                      ┌─────────────────────────────────────────┐
                      │               API GATEWAY               │
                      │  - JWT İmza ve Süre Doğrulama           │
                      │  - Public Whitelist (/auth, GET /prod)  │
                      │  - Claims Propagation:                  │
                      │    (X-User-Id, X-User-Roles Header Ekle)│
                      └───────────┬────────────────────────┬────┘
                                  │                        │
            /api/v1/auth/**       │                        │ /api/v1/orders/**
                                  ▼                        ▼
                      ┌──────────────────────┐   ┌──────────────────────┐
                      │   CUSTOMER SERVICE   │   │    ORDER SERVICE     │
                      │  (Kimlik & Auth Sağl.)│   │ (X-User-Id Header ile│
                      │  - BCrypt Şifreleme  │   │  kullanıcıyı tanır)  │
                      │  - JWT & Refresh Üret│   └──────────────────────┘
                      │  - OAuth2 Entegrasyon│
                      └──────────────────────┘
```

### 9.1. Kimlik ve Token Yönetimi (`customer-service`)
- **Normal Giriş (Password-Based)**: `POST /api/v1/auth/login` (BCrypt hash karşılaştırması, 15 dk Access Token + 7 gün Refresh Token üretimi).
- **Kullanıcı Kaydı (Register)**: `POST /api/v1/auth/register` (ACID veritabanı işleminde müşteri profili + kimlik bilgileri oluşturulur, Outbox olayı fırlatılır).
- **Token Yenileme (Refresh)**: `POST /api/v1/auth/refresh` (Süresi biten access token yeni bir token ile yenilenir).
- **OAuth2 / Sosyal Giriş (Google / GitHub)**: `POST /api/v1/auth/oauth2` (OAuth2 profil bilgileri alınır, varsa müşteriyle eşleştirilir, yoksa otomatik müşteri oluşturulup platform JWT'si üretilir).

### 9.2. Edge Security ve Token Relay (`api-gateway`)
- **Public Rotalar (Anonim Erişim)**: `/api/v1/auth/**`, `GET /api/v1/products/**`, `GET /api/v1/categories/**`, `/actuator/**`, `/fallback/**`.
- **Korumalı Rotalar**: `/api/v1/orders/**`, `/api/v1/payments/**`, `/api/v1/customers/**` için geçerli `Bearer <JWT>` zorunludur.
- **Claims Propagation**: Gateway JWT'yi doğruladıktan sonra token içindeki `sub` (User ID), `email` ve `role` bilgilerini ayıklayarak downstream servislere `X-User-Id`, `X-User-Email` ve `X-User-Roles` başlıkları olarak aktarır.
- **Hata Yanıtları**: Geçersiz veya eksik token durumlarında RFC 7807 uyumlu `401 Unauthorized ProblemDetail` dönülür.

---

---

## 10. Kurumsal Hazırlık ve Üretime Hazır Altyapı (Enterprise Production-Readiness)

Platform; kurumsal üretim ortamlarının gereksinim duyduğu 6 kritik dayanıklılık, performans ve gözlemlenebilirlik desenine tam uyumludur:

```text
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                        KURUMSAL ÜRETİME HAZIRLIK MİMARİSİ                              │
├──────────────────────────┬──────────────────────────┬──────────────────────────────────┤
│ 1. Redis Cache-Aside     │ 2. Saga Timeout Worker   │ 3. Redis Rate Limiter            │
│ (product-service)        │ (order-service)          │ (api-gateway)                    │
│ • Okuma Hızlandırma      │ • Askıda Sipariş Tespiti │ • Atomik Lua Token Bucket        │
│ • Sıkı TTL (15-60 dk)    │ • Otomatik Telafi Tetik  │ • IP & User-Id Bazlı Kotalar     │
│ • Invalidation Eviction  │ • orders.cancelled Olayı │ • 429 Too Many Requests          │
├──────────────────────────┼──────────────────────────┼──────────────────────────────────┤
│ 4. Flyway Migrations     │ 5. Merkezi Swagger UI    │ 6. Uçtan Uca Saga Testleri       │
│ (7 Mikroservis)          │ (api-gateway)            │ (order-service)                  │
│ • ddl-auto: validate     │ • /swagger-ui.html Hub   │ • Embedded Kafka Testleri        │
│ • V1__init_schema.sql    │ • 7 Servis Dropdown Menü │ • Ödeme Reddi & Kargo Telafisi   │
│ • Güvenli Şema Evrimi    │ • Bearer JWT Yetkilend.  │ • %100 Deterministik Doğrulama   │
└──────────────────────────┴──────────────────────────┴──────────────────────────────────┘
```

### 10.1. Redis Cache-Aside Deseni (`product-service`)
- **Trafik Ayrımı**: E-ticaret trafiğinin %95'ini oluşturan ürün ve kategori sorguları Redis önbelleğinden milisaniyeler içinde sunulur.
- **TTL Stratejisi**: Ürünler için 15 dakika, kategoriler için 60 dakika TTL tanımlıdır.
- **Önbellek Zehirlenmesi / Delinmesi (Penetration) Koruması**: `disableCachingNullValues()` ile var olmayan kayıtların önbelleğe doluşması engellenir.
- **Aktif Geçersiz Kılma (Eviction)**: Bir ürün veya kategori güncellendiğinde, silindiğinde veya stok değiştiğinde `@CacheEvict(allEntries = true)` ile önbellek anında temizlenir.

### 10.2. Saga Zaman Aşımı İşçisi (`OrderSagaTimeoutWorker` in `order-service`)
- **Problem**: Asenkron dağıtık mimaride zehirli mesajlar `.DLT` kuyruğuna taşındığında veya alt servisler geçici olarak yanıt veremediğinde siparişlerin sonsuza dek `PENDING` kalması riski.
- **Çözüm**: `@Scheduled(fixedDelay = 30000)` ile çalışan arka plan işçisi, SLA süresini (varsayılan 300 sn) aşan ve tamamlanmamış siparişleri tespit eder.
- **Otomatik Telafi**: Sipariş `CANCELLED` yapılır, `failureReason = "SAGA_TIMEOUT"` atanır ve Outbox tablosuna `OrderCancelled` olayı basılarak rezerve edilmiş stokların (`inventory.released`) serbest bırakılması sağlanır. Prometheus metriği (`order_saga_timeout_total`) artırılır.

### 10.3. Dağıtık Redis Token Bucket Rate Limiter (`api-gateway`)
- **Atomik Lua Scripti**: Race condition oluşmadan Redis üzerinde kayan pencere (Sliding Window) sayaç algoritması çalıştırılır.
- **Ayrık Kota Politikası**:
  - **Anonim İstemciler**: IP adresi başına dakikada 10 istek.
  - **Giriş Yapmış Müşteriler**: Kullanıcı ID'si (`X-User-Id` / JWT `sub`) başına dakikada 60 istek.
- **Standart Yanıt**: Limit aşıldığında RFC 7807 uyumlu `429 Too Many Requests ProblemDetail` ve `Retry-After: 60` başlığı dönülür.
- **Fail-Open Dayanıklılığı**: Redis geçici olarak kesilirse sistem trafiği bloke etmez, güvenlik logu yazarak fail-open modunda istekleri geçirmeye devam eder.

### 10.4. Versiyonlu Veritabanı Migrasyonları (Flyway)
- **Güvenli Şema Yönetimi**: Üretim ortamlarında `hibernate.ddl-auto: update` kullanımı yasaklanmış; yerine `hibernate.ddl-auto: validate` ve `flyway.enabled: true` devreye alınmıştır.
- **V1 Şemaları**: Her mikroservisin kendi izole veritabanı için (`product_db`, `order_db`, `payment_db`, `inventory_db`, `shipping_db`, `customer_db`, `notification_db`) PostgreSQL DDL tabloları, birincil/yabancı anahtarlar ve B-Tree indeksler `V1__init_schema.sql` dosyalarında versiyonlanmıştır.

### 10.5. Merkezi OpenAPI 3.0 & Swagger UI Portalı (`api-gateway`)
- **Tek Noktadan API Keşfi**: Geliştiriciler ve entegratörler API Gateway üzerinden `http://localhost:8080/swagger-ui.html` adresine giderek tek bir arayüzden tüm mikroservislerin API dokümantasyonuna erişebilir.
- **Canlı Şema Entegrasyonu**: Gateway, açılır menüdeki servis seçimlerine göre `/v3/api-docs/*` isteklerini ilgili mikroservise ters proxy ile yönlendirir.
- **İnteraktif Güvenlik**: Tüm servislerde `BearerAuth` JWT güvenlik şeması tanımlıdır; `Authorize` butonuna token yapıştırılarak korumalı uç noktalar doğrudan Swagger üzerinden test edilebilir.

### 10.6. Kapsamlı Saga Uçtan Uca Entegrasyon Testleri (`order-service`)
- `@EmbeddedKafka` ile harici servis bağımlılığı olmadan izole ortamda 6 ana iş akışı test edilmektedir:
  1. **Mutlu Yol (Happy Path)**: `inventory.reserved` + `payments.authorized` ➡️ Sipariş `CONFIRMED` ve Outbox'a `OrderConfirmed` yazılır.
  2. **Stok Başarısızlığı Telafisi**: `inventory.failed` ➡️ Sipariş `CANCELLED` ve `OrderCancelled` outbox olayı üretilir.
  3. **Ödeme Başarısızlığı Telafisi**: Stok rezerve edildikten sonra `payments.failed` gelir ➡️ Sipariş `CANCELLED` olur ve stok iadesi için telafi olayı tetiklenir.
  4. **Kullanıcı/İptal Emri Telafisi**: Müşteri rezervasyon aşamasında iptal ettiğinde telafi zinciri yürütülür.
  5. **Tam Yaşam Döngüsü**: Sipariş onayından sonra `shipments.created` olayı ile `SHIPPING_CREATED` durumuna geçiş doğrulanır.
  6. **Kesin İdempotency**: Kafka'dan gelen kopya olaylar tespit edilip güvenle yok sayılır.

---

## 11. Geliştirici ve Yapay Zeka Ajan Kılavuzları

Bu depoda insan geliştiricilerin yanı sıra **Antigravity**, **Gemini**, **Claude Code** ve **Cursor** gibi yapay zeka ajanları için yapılandırılmış kurallar bulunmaktadır:

- **[AGENTS.md](file:///D:/backend_projects/commerce/AGENTS.md)**: Proje genelindeki katı mimari kurallar, outbox deseni ve Kafka standartları.
- **[CLAUDE.md](file:///D:/backend_projects/commerce/CLAUDE.md)**: Claude Code için hızlı komutlar ve özet kurallar.
- **[GEMINI.md](file:///D:/backend_projects/commerce/GEMINI.md)**: Gemini/Antigravity ortam kuralları.
- Her mikroservisin klasöründe (ör. `order-service/AGENTS.md`) o servise özel domain modellerini ve durum makinelerini açıklayan yerel kılavuzlar mevcuttur.

---

## 12. Lisans
Bu proje açık kaynaklıdır ve eğitim/mühendislik referansı amacıyla geliştirilmiştir.
