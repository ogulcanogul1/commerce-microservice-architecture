# GEMINI.md - Antigravity ve Gemini Agent Çalışma Kuralları

Tüm mimari standartlar, olay zarfı tanımları, port dağılımları ve kodlama ilkeleri için lütfen [AGENTS.md](file:///D:/backend_projects/commerce/AGENTS.md) ve [CLAUDE.md](file:///D:/backend_projects/commerce/CLAUDE.md) dosyalarını inceleyin.

### Hızlı Kurallar Özeti
- **Dil ve Sürüm**: Java 21 LTS + Spring Boot 4.1.x.
- **İzolasyon**: Servis Başına Veritabanı (Database-Per-Service). Kesinlikle veritabanı paylaşımı veya çapraz SQL sorguları yapılamaz.
- **Saga Orkestrasyonu**: `order-service` tüm sipariş iş akışını yönetir ve hata anında telafi adımlarını tetikler.
- **Transactional Outbox**: Olaylar doğrudan Kafka'ya atılmaz, `outbox_events` tablosu üzerinden güvenli şekilde yayınlanır.
- **Idempotency**: Her Kafka tüketicisi `(consumer_group, event_id)` kontrolü ile yinelenen mesajları eler. Ödemelerde `Idempotency-Key` zorunludur.
- **Olay Formatı**: Tüm Kafka mesajları standart JSON zarfında (`eventId`, `eventType`, `aggregateId`, `aggregateType`, `timestamp`, `version`, `correlationId`, `causationId`, `payload`) olmalıdır.
- **Portlar**: Gateway (8080), Product (8081), Order (8082), Payment (8083), Inventory (8084), Shipping (8085), Customer (8086), Notification (8087).
- **Ayrıntılı Git Commit Mesajları**: Commit mesajlarında asla genel/soyut ifadeler (`add dtos`, `add service layer`) tek başına kullanılmamalıdır. Eklenen DTO sınıfları (ör. `CreateProductRequest`, `ProductResponse`), servisler (ör. `ProductService`, `CategoryService`) veya domain varlıkları başlıkta veya gövdede açıkça listelenmelidir.
- **İstisna Sınıflandırma Standardı (Retryable vs NonRetryable)**: Yeni eklenen domain hataları `BusinessRuleException` (`NonRetryable`) veya `TransientException` (`Retryable`) hiyerarşisine uymalıdır. İş kuralları ve 4xx hataları asla retry edilmez; fail-fast veya Saga telafi adımları tetiklenir.

