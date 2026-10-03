# CLAUDE.md - Bildirim Servisi (Notification Service) Rehberi

Bu servis `notification-service` modülü olup yalnızca Kafka olaylarını dinleyen (Pure Consumer) ve müşterilere E-posta / SMS gönderimlerini simüle eden servistir.

Detaylı teknik mimari ve kurallar için [AGENTS.md](file:///D:/backend_projects/commerce/notification-service/AGENTS.md) ve kök dizindeki [AGENTS.md](file:///D:/backend_projects/commerce/AGENTS.md) dosyalarına bakın.

### Hızlı Başvuru
- **Port**: `8087` | **Veritabanı**: `notification_db` (PostgreSQL)
- **Ana Roller**: Kafka Dinleyicisi, Müşteri Bildirim Şablonları, Spam Önleme (Idempotency Tablosu).
- **Dinlenen Olaylar**: `orders.confirmed`, `orders.cancelled`, `payments.failed`, `shipments.created`, `shipments.delivered`.
- **Komutlar**:
  - Derleme: `cd notification-service; .\mvnw clean compile; cd ..`
  - Test: `cd notification-service; .\mvnw test; cd ..`
  - Çalıştırma: `cd notification-service; .\mvnw spring-boot:run; cd ..`
