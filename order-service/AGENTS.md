# Sipariş Servisi (Order Service) - Geliştirme Yönergeleri (AGENTS.md)

> Bu belge, `order-service` için geçerli olan mimari kararları, Saga durum makinesini, Transactional Outbox yapısını ve Kafka konularını tanımlar.

---

## 1. Servis Genel Bakışı
- **Dizin**: `order-service`
- **Paket**: `com.dgl.order`
- **Varsayılan Port**: `8082`
- **Veritabanı**: `order_db` (PostgreSQL - 5432)
- **Rolü**: Sipariş Aggregate Kökü (Aggregate Root), Dağıtık Saga Orkestratörü, Transactional Outbox Yayıncısı

---

## 2. Sipariş Yaşam Döngüsü ve Durum Makinesi (State Machine)

Sipariş süreci katı bir durum makinesi ile yönetilir:

```text
       [Müşteri Sipariş Oluşturdu]
                  │
                  ▼
              PENDING
                  │
        (inventory.reserved)
                  ▼
          INVENTORY_RESERVED
                  │
        (payments.authorized)
                  ▼
          PAYMENT_AUTHORIZED
                  │
         (shipments.created)
                  ▼
              CONFIRMED (Başarılı Bitiş)
```

### Başarısızlık ve Telafi Durumları (Compensations):
- **Stok Rezerve Edilemezse (`inventory.failed`)**:
  - Durum: `INVENTORY_FAILED` -> `CANCELLED`
  - Olay: `orders.cancelled` yayınlanır.
- **Ödeme Alınamazsa (`payments.failed`)**:
  - Durum: `PAYMENT_FAILED` -> `CANCELLED`
  - Telafi: Rezerve edilen stoğun serbest bırakılması için `orders.cancelled` yayınlanır.
- **Kargo Oluşturulamazsa (`shipments.cancelled` / hata)**:
  - Durum: `SHIPPING_FAILED` -> `CANCELLED`
  - Telafi: Ödemenin iade edilmesi (`payments.refunded` için) ve stoğun serbest bırakılması tetiklenir.

---

## 3. Dağıtık Sistem Desenleri

### 3.1. Transactional Outbox Deseni
- Bir sipariş kaydedildiğinde veya durumu güncellendiğinde, Kafka olayı doğrudan gönderilmez.
- Aynı ACID veritabanı işleminde `outbox_events` tablosuna kayıt yazılır:
  - `id`: UUID (Primary Key)
  - `aggregate_type`: "Order"
  - `aggregate_id`: Sipariş ID (String)
  - `type`: Olay tipi (ör. `OrderCreated`, `OrderConfirmed`)
  - `payload`: Standart zarf JSON içeriği
  - `created_at`: UTC Zaman damgası
  - `status`: `PENDING` / `PUBLISHED` / `FAILED`
- Zamanlanmış bir servis (`@Scheduled`) veya Debezium CDC bu tabloyu okuyarak Kafka'ya güvenle yayınlar.

### 3.2. Kesin Idempotency (Tüketici Tekilleştirmesi)
- `order-service` gelen her alt servis olayını (`inventory.reserved`, `payments.authorized`, vb.) işlemeden önce `processed_events` tablosunda `(consumer_group, event_id)` çiftini denetler.
- Zaten işlenmiş bir olay gelirse hiçbir işlem yapılmadan `ACK` dönülür.

---

## 4. Kafka Konuları (Topics)

### Üretilen Olaylar (Produced):
- `orders.created` - Sipariş oluşturuldu (Stok servisine stok rezervasyonu komutu/olayı)
- `orders.confirmed` - Sipariş başarıyla tamamlandı (Bildirim servisine teslimat onayı)
- `orders.cancelled` - Sipariş iptal edildi (Stok ve ödeme servislerine telafi sinyali)

### Tüketilen Olaylar (Consumed):
- `inventory.reserved` - Stok başarıyla rezerve edildi -> Ödeme adımına geç
- `inventory.failed` - Yetersiz stok -> Siparişi iptal et
- `payments.authorized` - Ödeme provizyonu başarılı -> Kargo adımına geç
- `payments.failed` - Ödeme başarısız -> Telafi başlat (Stoğu bırak)
- `shipments.created` - Kargo kaydı açıldı -> Siparişi CONFIRMED yap

---

## 5. REST API Uç Noktaları

- `POST /api/orders` - Yeni sipariş oluşturur (`PENDING` durumuyla döner ve Outbox'a `orders.created` yazar).
- `GET /api/orders/{id}` - Sipariş detayını ve güncel Saga durumunu getirir.
- `GET /api/orders/customer/{customerId}` - Belirli bir müşterinin tüm siparişlerini listeler.
- `POST /api/orders/{id}/cancel` - Kullanıcı tarafından sipariş iptali başlatır.

---

## 6. Paket Mimarisi

```text
com.dgl.order
├── config/              # KafkaProducerConfig, KafkaConsumerConfig, JacksonConfig
├── controller/          # OrderController
├── domain/              # Order, OrderItem, OrderStatus (Entity & Value Objects)
├── dto/
│   ├── request/         # CreateOrderRequest
│   └── response/        # OrderResponse, OrderItemResponse
├── exception/           # OrderNotFoundException, InvalidOrderStateException
├── messaging/
│   ├── event/           # Standard EventEnvelope, OrderCreatedPayload vb.
│   ├── producer/        # OrderEventProducer
│   └── consumer/        # InventoryResponseConsumer, PaymentResponseConsumer, ShippingResponseConsumer
├── outbox/              # OutboxEvent (Entity), OutboxRepository, OutboxPublisher
├── repository/           # OrderRepository, ProcessedEventRepository
└── service/             # OrderService, OrderSagaOrchestrator
```

---

## 7. Derleme ve Test Komutları

```powershell
cd order-service
.\mvnw clean compile
.\mvnw test
.\mvnw spring-boot:run
cd ..
```
