# CLAUDE.md - Stok Servisi (Inventory Service) Rehberi

Bu servis `inventory-service` modülü olup bağımsız stok veritabanı, rezervasyon yaşam döngüsü, süre aşımı (TTL) ve aşırı satışı (overselling) önleyen eşzamanlılık kontrolünden sorumludur.

Detaylı teknik mimari ve kurallar için [AGENTS.md](file:///D:/backend_projects/commerce/inventory-service/AGENTS.md) ve kök dizindeki [AGENTS.md](file:///D:/backend_projects/commerce/AGENTS.md) dosyalarına bakın.

### Hızlı Başvuru
- **Port**: `8084` | **Veritabanı**: `inventory_db` (PostgreSQL)
- **Ana Roller**: Stok Takibi, Rezervasyon, Süre Aşımı Bırakma, İyimser Kilitleme (`@Version`), Outbox.
- **Olaylar**: `orders.created` dinlenir -> `inventory.reserved` veya `inventory.failed` üretilir.
- **Telafi**: `orders.cancelled` dinlenir -> `inventory.released` üretilir.
- **Komutlar**:
  - Derleme: `cd inventory-service; .\mvnw clean compile; cd ..`
  - Test: `cd inventory-service; .\mvnw test; cd ..`
  - Çalıştırma: `cd inventory-service; .\mvnw spring-boot:run; cd ..`
