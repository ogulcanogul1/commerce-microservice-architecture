# CLAUDE.md - Ödeme Servisi (Payment Service) Rehberi

Bu servis `payment-service` modülü olup finansal işlemlerin güvenliğinden, katı idempotency kontrolünden ve iade mekanizmalarından sorumludur.

Detaylı teknik mimari ve kurallar için [AGENTS.md](file:///D:/backend_projects/commerce/payment-service/AGENTS.md) ve kök dizindeki [AGENTS.md](file:///D:/backend_projects/commerce/AGENTS.md) dosyalarına bakın.

### Hızlı Başvuru
- **Port**: `8083` | **Veritabanı**: `payment_db` (PostgreSQL)
- **Ana Roller**: Ödeme Alma, Provizyon, İade, Idempotency Tablosu, Transactional Outbox.
- **Zorunlu Başlık**: `Idempotency-Key` (Ödeme API çağrılarında çift tahsilatı önlemek için).
- **Durumlar**: `PENDING`, `AUTHORIZED`, `CAPTURED`, `FAILED`, `REFUNDED`.
- **Komutlar**:
  - Derleme: `cd payment-service; .\mvnw clean compile; cd ..`
  - Test: `cd payment-service; .\mvnw test; cd ..`
  - Çalıştırma: `cd payment-service; .\mvnw spring-boot:run; cd ..`
