# CLAUDE.md - Ürün Servisi (Product Service) Rehberi

Bu servis `product-service` modülü olup ürün kataloğu, fiyatlandırma, kategoriler ve Redis tabanlı yüksek performanslı Cache-Aside önbellek yönetiminden sorumludur.

Detaylı teknik mimari ve kurallar için [AGENTS.md](file:///D:/backend_projects/commerce/product-service/AGENTS.md) ve kök dizindeki [AGENTS.md](file:///D:/backend_projects/commerce/AGENTS.md) dosyalarına bakın.

### Hızlı Başvuru
- **Port**: `8081` | **Veritabanı**: `product_db` (PostgreSQL) + Redis (Önbellek)
- **Ana Roller**: Ürün Kataloğu, Fiyat Yönetimi, Redis Cache-Aside, Sıkı TTL ve Eviction.
- **Performans Kuralı**: `GET /api/products/{id}` istekleri Redis önbelleğinden karşılanmalıdır. Güncelleme anında önbellek geçersiz kılınmalıdır (`@CacheEvict`).
- **Komutlar**:
  - Derleme: `cd product-service; .\mvnw clean compile; cd ..`
  - Test: `cd product-service; .\mvnw test; cd ..`
  - Çalıştırma: `cd product-service; .\mvnw spring-boot:run; cd ..`
