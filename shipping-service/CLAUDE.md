# CLAUDE.md - Kargo Servisi (Shipping Service) Rehberi

Bu servis `shipping-service` modülü olup kargo kaydı oluşturma, takip numarası tahsisi ve teslimat yaşam döngüsünden sorumludur.

Detaylı teknik mimari ve kurallar için [AGENTS.md](file:///D:/backend_projects/commerce/shipping-service/AGENTS.md) ve kök dizindeki [AGENTS.md](file:///D:/backend_projects/commerce/AGENTS.md) dosyalarına bakın.

### Hızlı Başvuru
- **Port**: `8085` | **Veritabanı**: `shipping_db` (PostgreSQL)
- **Ana Roller**: Kargo Kaydı, Takip Numarası Üretimi, Gönderi Takibi, Telafi İptalleri.
- **Durumlar**: `PENDING -> CREATED -> IN_TRANSIT -> DELIVERED` (veya `CANCELLED`).
- **Olaylar**: `shipments.created`, `shipments.cancelled`, `shipments.delivered`.
- **Komutlar**:
  - Derleme: `cd shipping-service; .\mvnw clean compile; cd ..`
  - Test: `cd shipping-service; .\mvnw test; cd ..`
  - Çalıştırma: `cd shipping-service; .\mvnw spring-boot:run; cd ..`
