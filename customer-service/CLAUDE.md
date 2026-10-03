# CLAUDE.md - Müşteri Servisi (Customer Service) Rehberi

Bu servis `customer-service` modülü olup müşteri profilleri, kayıtlı teslimat adresleri ve kullanıcı tercihlerinin yönetiminden sorumludur.

Detaylı teknik mimari ve kurallar için [AGENTS.md](file:///D:/backend_projects/commerce/customer-service/AGENTS.md) ve kök dizindeki [AGENTS.md](file:///D:/backend_projects/commerce/AGENTS.md) dosyalarına bakın.

### Hızlı Başvuru
- **Port**: `8086` | **Veritabanı**: `customer_db` (PostgreSQL)
- **Ana Roller**: Müşteri Kaydı, Adres Defteri, Profil Güncelleme, `customers.updated` Olayı.
- **Komutlar**:
  - Derleme: `cd customer-service; .\mvnw clean compile; cd ..`
  - Test: `cd customer-service; .\mvnw test; cd ..`
  - Çalıştırma: `cd customer-service; .\mvnw spring-boot:run; cd ..`
