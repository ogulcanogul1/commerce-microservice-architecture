# CLAUDE.md - Claude Code İçin Geliştirme Yönergeleri

> Bu belge, Claude Code asistanının **Commerce Platform** reposunda çalışırken takip etmesi gereken mimari kuralları, derleme komutlarını ve kodlama standartlarını içerir.

## Proje Özeti
Bu depo; **Java 21** ve **Spring Boot 4.x / Spring Cloud** ile geliştirilen, dağıtık sistemler problemlerine odaklanmış, olay güdümlü (event-driven) mikroservis tabanlı bir e-ticaret platformudur.

Detaylı küresel mimari ve standartlar için [AGENTS.md](file:///D:/backend_projects/commerce/AGENTS.md) ve [project/project.md](file:///D:/backend_projects/commerce/project/project.md) dosyalarına bakın.

---

## 1. Hızlı Başvuru: Servis Port ve Veritabanı Haritası

| Servis Adı | Port | Veritabanı | Birincil Sorumluluk |
| :--- | :--- | :--- | :--- |
| `api-gateway` | `8080` | Redis | Dinamik yönlendirme, JWT doğrulama, hız sınırı (rate limit), circuit breaker |
| `product-service` | `8081` | `product_db` / Redis | Ürün kataloğu, kategoriler, fiyat, Redis Cache-Aside önbellekleme |
| `order-service` | `8082` | `order_db` | Sipariş yönetimi, Saga orkestrasyonu, Transactional Outbox |
| `payment-service` | `8083` | `payment_db` | Idempotent ödeme provizyonu ve tahsilatı, iade işlemleri |
| `inventory-service` | `8084` | `inventory_db` | Stok rezervasyonu, süre aşımı (TTL), iyimser kilitleme (@Version) |
| `shipping-service` | `8085` | `shipping_db` | Kargo süreçleri, takip numarası üretimi, lojistik simülasyonu |
| `customer-service` | `8086` | `customer_db` | Müşteri profili ve adres yönetimi |
| `notification-service` | `8087` | `notification_db` | Asenkron e-posta / SMS bildirim simülasyonu |

---

## 2. Derleme, Test ve Çalıştırma Komutları

Tüm servisler Maven wrapper (`mvnw.cmd` / `mvnw`) ile yönetilir (Windows PowerShell ortamı):

```powershell
# Tek bir servisi derlemek
cd <servis-dizini>; .\mvnw clean compile; cd ..

# Testleri atlayarak paketlemek
cd <servis-dizini>; .\mvnw clean package -DskipTests; cd ..

# Birim ve entegrasyon testlerini çalıştırmak
cd <servis-dizini>; .\mvnw test; cd ..

# Servisi yerel ortamda çalıştırmak
cd <servis-dizini>; .\mvnw spring-boot:run; cd ..
```

---

## 3. Temel Mimari Kurallar ve Kısıtlamalar

1. **Bağımsız Mikroservis İzolasyonu**:
   - Asla ortak veritabanı kullanılmaz. Başka bir servisin veritabanına bağlanılamaz.
   - Kod seviyesinde servisler arası doğrudan import yapılamaz.
   - Bütün süreçler Kafka olayları üzerinden asenkron yürütülür.
2. **Saga Orkestrasyonu (`order-service`)**:
   - Akış: `Sipariş Oluştur -> Stok Rezerve Et -> Ödeme Al -> Kargo Oluştur -> Sipariş Onayla`.
   - Adımlardan biri başarısız olduğunda ters sırada telafi (compensation) olayları fırlatılmalıdır.
3. **Transactional Outbox Deseni**:
   - `@Transactional` içinde doğrudan Kafka gönderimi yapılmaz.
   - Olaylar veritabanındaki `outbox_events` tablosuna yazılır ve arka plan poller ile Kafka'ya iletilir.
4. **Kesin Idempotency (Tekilleştirme)**:
   - Kafka tüketici metotları `processed_events` tablosunu kontrol ederek yinelenen mesajları işlememelidir.
   - `POST /payments` isteklerinde `Idempotency-Key` başlığı aranmalıdır.
5. **Standart Olay Şeması (Event Envelope)**:
   - Kafka mesajları şu alanları içermelidir:
     `{ eventId, eventType, aggregateId, aggregateType, timestamp, version, correlationId, causationId, payload }`.
6. **Kodlama Standartları**:
   - DTO ve Event tanımları için Java 21 `record` kullanılmalıdır.
   - Jakarta Bean Validation zorunludur (`@Valid`, `@NotNull`, `@NotBlank`).
   - Hata cevapları RFC 7807 `ProblemDetails` standardında olmalıdır.
7. **Ayrıntılı Git Commit Standartları**:
   - Commit mesajlarında genel ve soyut başlıklar (`add dtos`, `add service layer`) yerine eklenen sınıfların ve servislerin isimleri açıkça belirtilmelidir (ör. `feat(product): add dtos (Create/UpdateProduct, ProductResponse)`, `feat(product): add service layer (ProductService, CategoryService)`).

---

## 4. Servis Düzeyi Detaylar
Her servisin dizinindeki `AGENTS.md` ve `CLAUDE.md` dosyalarında o servise ait özel domain modelleri, durum makineleri ve Kafka konuları yer almaktadır.
