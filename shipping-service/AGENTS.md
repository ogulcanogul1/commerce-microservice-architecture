# Kargo Servisi (Shipping Service) - Geliştirme Yönergeleri (AGENTS.md)

> Bu belge, `shipping-service` için geçerli olan mimari kararları, kargo durum yönetimini, takip mekanizmasını ve Kafka konularını tanımlar.

---

## 1. Servis Genel Bakışı
- **Dizin**: `shipping-service`
- **Paket**: `com.dgl.shipping`
- **Varsayılan Port**: `8085`
- **Veritabanı**: `shipping_db` (PostgreSQL - 5432)
- **Rolü**: Gönderi kaydı oluşturma, kargo takip kodu üretimi, lojistik taşıyıcı simülasyonu ve teslimat takibi

---

## 2. Kargo Durum Makinesi (Shipment Status)

```text
       [Ödeme Tamamlandı / Kargo Emri]
                      │
                      ▼
                   PENDING
                      │
                      ▼
                   CREATED (Takip Kodu Üretildi)
                      │
            ┌─────────┴─────────┐
            ▼                   ▼
        IN_TRANSIT          CANCELLED (Sipariş İptal Edildi)
            │
            ▼
        DELIVERED (Teslim Edildi)
```

---

## 3. Dağıtık Sistem Desenleri ve Kurallar

### 3.1. Telafi (Compensation) Desteği
- Eğer kargo oluşturulduktan sonraki bir adımda (veya kullanıcı talebiyle) sipariş iptal edilirse, kargo durumu `CANCELLED` olarak güncellenir ve `shipments.cancelled` olayı yayınlanır.

### 3.2. Transactional Outbox
- Tüm kargo durumu değişiklikleri `outbox_events` tablosu üzerinden Kafka'ya asenkron olarak güvenle aktarılır.

---

## 4. Kafka Konuları (Topics)

### Üretilen Olaylar (Produced):
- `shipments.created` - Kargo kaydı açıldı, takip kodu üretildi (Sipariş servisi siparişi CONFIRMED yapar).
- `shipments.cancelled` - Kargo gönderisi iptal edildi (Lojistik iptal bildirimi).
- `shipments.delivered` - Kargo alıcıya ulaştı (Bildirim servisi teslimat mesajı gönderir).

### Tüketilen Olaylar (Consumed):
- `orders.cancelled` - Eğer paket henüz yola çıkmamışsa kargo gönderisini iptal eder.

---

## 5. REST API Uç Noktaları

- `POST /api/shipping` - Yeni kargo gönderi kaydı oluşturur.
- `GET /api/shipping/{id}` - Kargo detayını döner.
- `GET /api/shipping/track/{trackingNumber}` - Takip numarasıyla kargo durumunu sorgular.
- `POST /api/shipping/{id}/status` - Kargo durumunu günceller (`IN_TRANSIT`, `DELIVERED`).
- `POST /api/shipping/{id}/cancel` - Kargo gönderisini iptal eder.

---

## 6. Paket Mimarisi

```text
com.dgl.shipping
├── config/              # KafkaConfig, DatabaseConfig
├── controller/          # ShippingController
├── domain/              # Shipment, ShipmentStatus, Address, Carrier
├── dto/
│   ├── request/         # CreateShipmentRequest, UpdateStatusRequest
│   └── response/        # ShipmentResponse, TrackingResponse
├── exception/           # ShipmentNotFoundException, InvalidShippingStateException
├── messaging/
│   ├── event/           # ShipmentCreatedPayload, ShipmentDeliveredPayload
│   ├── producer/        # ShippingEventProducer
│   └── consumer/        # OrderCancelledConsumer
├── outbox/              # OutboxEvent, OutboxRepository, OutboxPublisher
├── repository/           # ShipmentRepository
└── service/             # ShippingService, TrackingNumberGenerator
```

---

## 7. Derleme ve Test Komutları

```powershell
cd shipping-service
.\mvnw clean compile
.\mvnw test
.\mvnw spring-boot:run
cd ..
```
