# Ödeme Servisi (Payment Service) - Geliştirme Yönergeleri (AGENTS.md)

> Bu belge, `payment-service` için geçerli olan mimari kararları, idempotency gereksinimlerini, finansal durum yönetimini ve Kafka konularını tanımlar.

---

## 1. Servis Genel Bakışı
- **Dizin**: `payment-service`
- **Paket**: `com.dgl.payment`
- **Varsayılan Port**: `8083`
- **Veritabanı**: `payment_db` (PostgreSQL - 5432)
- **Rolü**: Ödeme provizyonu, tahsilat, iade ve katı idempotency denetimi

Finansal işlemler söz konusu olduğunda sistemin temel kuralı: **"Bir ödeme komutu asla ve hiçbir koşulda iki kez işlenemez."**

---

## 2. Temel İlkeler ve Dağıtık Sistem Desenleri

### 2.1. Katı Idempotency (Tekilleştirme)
- Tüm doğrudan ödeme API isteklerinde (`POST /api/payments`) HTTP başlığı olarak `Idempotency-Key` zorunludur.
- Veritabanında `idempotency_records` tablosu tutulur:
  - `idempotency_key`: İstek başlığındaki tekil anahtar (Primary Key / Unique Index).
  - `request_hash`: Gelen istek gövdesinin SHA-256 özeti (aynı anahtarla farklı veri gönderilmesini engeller).
  - `response_payload`: Başarılı ilk yanıtın JSON hali.
  - `status`: `IN_PROGRESS`, `COMPLETED`, `FAILED`.
  - `created_at`: Kayıt zamanı.
- Aynı `Idempotency-Key` ile tekrar gelen isteklerde ödeme işlemi tekrarlanmaz; veritabanında saklanan önceki yanıt doğrudan döner.

### 2.2. Transactional Outbox
- Ödeme durumu değiştiğinde (`AUTHORIZED`, `CAPTURED`, `FAILED`, `REFUNDED`), ilgili olay `outbox_events` tablosuna yazılır ve Kafka'ya oradan aktarılır.

---

## 3. Ödeme Durum Makinesi (Payment Status)

```text
       [Ödeme Talebi]
             │
             ▼
          PENDING
             │
      ┌──────┴──────┐
      ▼             ▼
  AUTHORIZED      FAILED
      │
      ▼
   CAPTURED
      │
      ▼ (Sipariş iptali / Telafi)
   REFUNDED
```

---

## 4. Kafka Konuları (Topics)

### Üretilen Olaylar (Produced):
- `payments.authorized` - Ödeme ön onayı alındı (Saga kargo adımına devam edebilir).
- `payments.captured` - Para hesaptan başarıyla tahsil edildi.
- `payments.failed` - Ödeme yetersiz bakiye, banka hatası veya sahtekarlık nedeniyle reddedildi.
- `payments.refunded` - Sipariş iptali sonucunda iade işlemi gerçekleştirildi.

### Tüketilen Olaylar (Consumed):
- `orders.cancelled` - Eğer bu sipariş için ödeme yapılmışsa otomatik telafi iadesi (`REFUNDED`) başlatılır.

---

## 5. REST API Uç Noktaları

- `POST /api/payments` - Yeni ödeme işlemi (`Idempotency-Key` başlığı ZORUNLUDUR).
- `GET /api/payments/{id}` - Ödeme detayını sorgular.
- `GET /api/payments/order/{orderId}` - Siparişe ait ödeme kaydını döner.
- `POST /api/payments/{id}/refund` - Ödeme iadesini başlatır.

---

## 6. Paket Mimarisi

```text
com.dgl.payment
├── config/              # IdempotencyFilter, KafkaConfig
├── controller/          # PaymentController
├── domain/              # Payment, PaymentStatus, PaymentMethod (Entities)
├── dto/
│   ├── request/         # ProcessPaymentRequest
│   └── response/        # PaymentResponse
├── exception/           # PaymentFailedException, IdempotencyConflictException
├── messaging/
│   ├── event/           # PaymentAuthorizedPayload, PaymentFailedPayload vb.
│   ├── producer/        # PaymentEventProducer
│   └── consumer/        # OrderCancelledConsumer
├── outbox/              # OutboxEvent, OutboxRepository, OutboxPublisher
├── repository/           # PaymentRepository, IdempotencyRecordRepository
└── service/             # PaymentService, IdempotencyService
```

---

## 7. Derleme ve Test Komutları

```powershell
cd payment-service
.\mvnw clean compile
.\mvnw test
.\mvnw spring-boot:run
cd ..
```
