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

## 7. Geliştirici ve Yapay Zeka Ajan Kılavuzları

Bu depoda insan geliştiricilerin yanı sıra **Antigravity**, **Gemini**, **Claude Code** ve **Cursor** gibi yapay zeka ajanları için yapılandırılmış kurallar bulunmaktadır:

- **[AGENTS.md](file:///D:/backend_projects/commerce/AGENTS.md)**: Proje genelindeki katı mimari kurallar, outbox deseni ve Kafka standartları.
- **[CLAUDE.md](file:///D:/backend_projects/commerce/CLAUDE.md)**: Claude Code için hızlı komutlar ve özet kurallar.
- **[GEMINI.md](file:///D:/backend_projects/commerce/GEMINI.md)**: Gemini/Antigravity ortam kuralları.
- Her mikroservisin klasöründe (ör. `order-service/AGENTS.md`) o servise özel domain modellerini ve durum makinelerini açıklayan yerel kılavuzlar mevcuttur.

---

## 8. Lisans
Bu proje açık kaynaklıdır ve eğitim/mühendislik referansı amacıyla geliştirilmiştir.
