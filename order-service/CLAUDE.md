# CLAUDE.md - Sipariş Servisi (Order Service) Rehberi

Bu servis `order-service` modülü olup sistemin iş akışı ve Saga orkestrasyon merkezidir.

Detaylı Saga durum makinesi, outbox yapısı ve kurallar için [AGENTS.md](file:///D:/backend_projects/commerce/order-service/AGENTS.md) ve kök dizindeki [AGENTS.md](file:///D:/backend_projects/commerce/AGENTS.md) dosyalarına bakın.

### Hızlı Başvuru
- **Port**: `8082` | **Veritabanı**: `order_db` (PostgreSQL)
- **Ana Roller**: Sipariş Yaşam Döngüsü, Saga Orkestratörü, Transactional Outbox, Tüketici Idempotency.
- **Durum Akışı**: `PENDING -> INVENTORY_RESERVED -> PAYMENT_AUTHORIZED -> SHIPPING_CREATED -> CONFIRMED`.
- **Hata Durumları**: `INVENTORY_FAILED`, `PAYMENT_FAILED`, `SHIPPING_FAILED`, `CANCELLED`.
- **Komutlar**:
  - Derleme: `cd order-service; .\mvnw clean compile; cd ..`
  - Test: `cd order-service; .\mvnw test; cd ..`
  - Çalıştırma: `cd order-service; .\mvnw spring-boot:run; cd ..`
