# Stok Servisi (Inventory Service) - Geliştirme Yönergeleri (AGENTS.md)

> Bu belge, `inventory-service` için geçerli olan mimari kararları, eşzamanlılık (concurrency) yönetimini, stok rezervasyon mekanizmasını ve Kafka konularını tanımlar.

---

## 1. Servis Genel Bakışı
- **Dizin**: `inventory-service`
- **Paket**: `com.dgl.inventory`
- **Varsayılan Port**: `8084`
- **Veritabanı**: `inventory_db` (PostgreSQL - 5432)
- **Rolü**: Stok takibi, rezervasyon yönetimi, TTL ile süre aşımı kontrolü, aşırı satışı (overselling) önleme

Stok veritabanı, sipariş veritabanından tamamen izoledir. Stok durumu yalnızca bu servis tarafından yönetilir.

---

## 2. Temel İlkeler ve Dağıtık Sistem Desenleri

### 2.1. Eşzamanlılık Kontrolü ve Aşırı Satışı Önleme (Overselling Prevention)
- Aynı anda birden fazla müşteri son ürünü almaya çalıştığında yarış durumu (race condition) oluşmaması için:
  - Varlık (Entity) seviyesinde JPA `@Version` ile **İyimser Kilitleme (Optimistic Locking)** uygulanır.
  - Yüksek çekişmeli (high-contention) ürünlerde gerekirse veritabanı seviyesinde `PESSIMISTIC_WRITE` kilidi kullanılır.
  - `availableQuantity = totalQuantity - reservedQuantity`. Kullanılabilir miktar asla sıfırın altına düşemez.

### 2.2. Stok Rezervasyon ve Süre Aşımı (TTL / Reservation Expiration)
- Sipariş oluşturulduğunda stok doğrudan düşülmez, **rezerve** edilir (`reservedQuantity` artar).
- Her rezervasyon kaydının bir son geçerlilik zamanı (`expires_at`, örneğin 15 dakika) bulunur.
- Ödeme belirli süre içinde tamamlanmazsa veya iptal olayı gelirse arka plan zamanlayıcısı stok rezervasyonunu serbest bırakır.

### 2.3. Transactional Outbox
- Rezervasyon başarılı (`inventory.reserved`), başarısız (`inventory.failed`) veya iptal (`inventory.released`) olduğunda olaylar `outbox_events` üzerinden Kafka'ya aktarılır.

---

## 3. Kafka Konuları (Topics)

### Üretilen Olaylar (Produced):
- `inventory.reserved` - İstenen miktarlar başarıyla rezerve edildi (Sipariş servisi ödeme adımına geçer).
- `inventory.failed` - Yetersiz stok nedeniyle rezervasyon yapılamadı (Sipariş servisi siparişi iptal eder).
- `inventory.released` - İptal veya süre aşımı nedeniyle rezerve stok geri bırakıldı.

### Tüketilen Olaylar (Consumed):
- `orders.created` - Yeni sipariş geldiğinde stok kontrolü ve rezervasyon başlatır.
- `orders.cancelled` - Sipariş iptal edildiğinde rezerve edilmiş stoğu anında serbest bırakır.

---

## 4. REST API Uç Noktaları

- `GET /api/inventory/{sku}` - Belirli bir SKU'nun stok ve rezervasyon durumunu döner.
- `POST /api/inventory` - Yeni stok kalemi tanımlar veya mevcut stoğu günceller (Tedarik/Depo girişi).
- `POST /api/inventory/reserve` - Senkron stok rezervasyon testi / API çağrısı.
- `POST /api/inventory/release` - Manuel stok serbest bırakma uç noktası.

---

## 5. Paket Mimarisi

```text
com.dgl.inventory
├── config/              # KafkaConfig, DatabaseConfig
├── controller/          # InventoryController
├── domain/              # InventoryItem, StockReservation, ReservationStatus
├── dto/
│   ├── request/         # ReserveStockRequest, AddStockRequest
│   └── response/        # InventoryResponse, ReservationResponse
├── exception/           # InsufficientStockException, InventoryNotFoundException
├── messaging/
│   ├── event/           # InventoryReservedPayload, InventoryFailedPayload vb.
│   ├── producer/        # InventoryEventProducer
│   └── consumer/        # OrderCreatedConsumer, OrderCancelledConsumer
├── outbox/              # OutboxEvent, OutboxRepository, OutboxPublisher
├── repository/           # InventoryRepository, StockReservationRepository
└── service/             # InventoryService, StockReservationScheduler
```

---

## 6. Derleme ve Test Komutları

```powershell
cd inventory-service
.\mvnw clean compile
.\mvnw test
.\mvnw spring-boot:run
cd ..
```
