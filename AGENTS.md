# Ticaret Platformu (Commerce Platform) - Ajan ve Mühendislik Kuralları (AGENTS.md)

> Bu belge, **Commerce Platform** reposundaki tüm yapay zeka ajanları (Antigravity, Gemini, Claude, Cursor) ve yazılım mühendisleri için geçerli olan mimari kararları, teknik standartları ve geliştirme kurallarını tanımlar.

---

## 1. Proje Vizyonu ve Temel Mühendislik İlkesi

Bu proje; basit CRUD operasyonları yerine gerçek dünya dağıtık sistem (distributed systems) zorlukları etrafında tasarlanmış, üretime hazır (production-grade), olay güdümlü (event-driven) ve bulut tabanlı bir e-ticaret platformudur.

### Temel Mühendislik Sorusu:
> **"Hangi dağıtık sistem problemini çözüyorum ve bunu çözmek için hangi teknoloji/tasarım deseni uygundur?"**

Teknolojiler sadece popüler oldukları için eklenmez. Her mimari karar doğrudan dağıtık bir sistem ihtiyacına yanıt verir:

| Dağıtık Sistem Problemi | Çözüm Deseni / Teknoloji |
| :--- | :--- |
| **Dağıtık İşlemler (Distributed Transactions)** | Orkestre Edilmiş Saga Deseni (`order-service`) |
| **Güvenilir Olay Yayınlama (Reliable Event Publishing)** | Transactional Outbox Deseni + Debezium / CDC Poller |
| **Veritabanı - Olay Senkronizasyonu** | Debezium / Kafka Connect ile Change Data Capture (CDC) |
| **Yinelenen Mesaj İşleme (Duplicate Messages)** | Kesin Tüketici ve Üretici Idempotency (Tekilleştirme Tablosu) |
| **Bağımsız Okuma/Yazma Ölçekleme** | CQRS (Command Query Responsibility Segregation) |
| **Yüksek Okuma Performansı (Ürün Kataloğu)** | Redis Cache-Aside Deseni (Sıkı TTL ve Eviction) |
| **Zehirli Mesajlar ve Geçici Hatalar** | Üstel Geri Çekilme (Exponential Backoff) + Dead Letter Queue (`.DLT`) |
| **Geçici Servis Kesintileri** | Devre Kesici (Resilience4j Circuit Breaker) + Zarif Geri Dönüşler (Fallback) |
| **Dağıtık İzleme ve Bağlam Taşıma** | OpenTelemetry + `X-Correlation-Id` ve `X-Causation-Id` başlıkları |
| **Trafik Şekillendirme ve Kimlik Doğrulama** | Spring Cloud Gateway + Redis Rate Limiter + OAuth2 / JWT |

---

## 2. Global Mimari Kurallar (Değiştirilemez / Non-Negotiable)

1. **Servis Başına Veritabanı (Database-Per-Service - Kesinlikle Paylaşımsız)**:
   - Her mikroservis yalnızca kendi izole PostgreSQL veritabanına sahiptir.
   - **KESİNLİKLE** başka bir servisin veritabanına doğrudan bağlanılamaz, SQL join yapılamaz veya tablolarına sorgu atılamaz.
   - Servisler arası veri gereksinimleri yalnızca asenkron Kafka olayları (Read Model) veya API Gateway üzerinden kimlik doğrulamalı REST/gRPC çağrılarıyla sağlanır.

2. **Olay Güdümlü İletişim (Kafka Backbone)**:
   - Senkron HTTP iletişimi sadece istemci-gateway ve gateway-servis yönlendirmeleri ile sınırlandırılmıştır.
   - Temel iş akışları (Sipariş -> Stok -> Ödeme -> Kargo) servisler arasında KESİNLİKLE Apache Kafka üzerinden asenkron olaylarla yönetilir.

3. **Standart Olay Zarfı (Unified Event Envelope)**:
   - Kafka'ya iletilen TÜM olaylar aşağıdaki standart JSON zarf şemasına uymak ZORUNDADIR:
   ```json
   {
     "eventId": "UUIDv4",
     "eventType": "OrderCreated",
     "aggregateId": "ORD-12345",
     "aggregateType": "Order",
     "timestamp": "2026-10-03T19:30:00Z",
     "version": 1,
     "correlationId": "UUIDv4",
     "causationId": "UUIDv4",
     "payload": { ... }
   }
   ```
   - **Alan Açıklamaları**:
     - `eventId`: Olayın tekil UUID kimliği.
     - `eventType`: PascalCase domain olay adı (ör. `OrderCreated`, `InventoryReserved`).
     - `aggregateId`: İlgili aggregate kök kimliği (ör. `ORD-12345`).
     - `aggregateType`: Aggregate adı (ör. `Order`, `Payment`, `Inventory`).
     - `timestamp`: UTC ISO-8601 formatında zaman damgası.
     - `version`: Olay şeması sürümü (şema evrimi için).
     - `correlationId`: Tüm servisler boyunca iş akışını baştan sona izleyen ortak ID.
     - `causationId`: Bu olayın tetiklenmesine neden olan komut veya bir önceki olayın ID'si.
     - `payload`: İlgili domaine özgü JSON veri nesnesi.

4. **Transactional Outbox Deseni**:
   - Spring `@Transactional` metotları içerisinde doğrudan Kafka'ya mesaj gönderilmez (Çift Yazma / Dual-Write riskini önlemek için).
   - Domain varlığı ile fırlatılacak olay kaydı aynı ACID veritabanı işlemi içerisinde `outbox_events` tablosuna yazılır.
   - Arka plandaki Outbox Poller veya CDC işlemi bu olayları okuyup en az bir kez teslimat (`at-least-once`) garantisiyle Kafka'ya basar.

5. **Sıkı Idempotency (Tekilleştirme)**:
   - Kafka "en az bir kez" (at-least-once) teslimat garantisi sunduğundan tüketiciler (consumer) kopya mesaj alabilir.
   - Tüm tüketici servisler `idempotent_consumers` / `processed_events` tablosunda `(consumer_group, event_id)` kaydı tutarak yinelenen mesajları görmezden gelmelidir.
   - Ödeme uç noktaları `Idempotency-Key` HTTP başlığını zorunlu tutmalıdır.

6. **Dağıtık İzleme (Correlation ID)**:
   - API Gateway her gelen istek için `X-Correlation-Id` üretir veya mevcut olanı doğrular.
   - Bu ID hem log MDC (Mapped Diagnostic Context) hem de Kafka mesaj başlıklarına kesintisiz aktarılmalıdır.

---

## 3. Servis Kataloğu, Portlar ve Veritabanları

| Servis Dizini | Paket Adı | Varsayılan Port | Veritabanı | Birincil Görev |
| :--- | :--- | :--- | :--- | :--- |
| `api-gateway` | `com.dgl.gateway` | **8080** | Redis (6379) | API Gateway, Yetkilendirme, Hız Sınırı (Rate Limit), Circuit Breaker |
| `product-service` | `com.dgl.product` | **8081** | `product_db` (5432) | Ürün kataloğu, kategoriler, fiyatlandırma, Redis önbellek |
| `order-service` | `com.dgl.order` | **8082** | `order_db` (5432) | Sipariş yönetimi, Saga Orkestratörü, Outbox olayları |
| `payment-service` | `com.dgl.payment` | **8083** | `payment_db` (5432) | Ödeme provizyonu ve tahsilat, Idempotency, İade işlemleri |
| `inventory-service`| `com.dgl.inventory`| **8084** | `inventory_db` (5432)| Stok rezervasyonu, TTL ile süre aşımı, İyimser Kilitleme |
| `shipping-service` | `com.dgl.shipping` | **8085** | `shipping_db` (5432) | Kargo gönderimi, takip kodu, lojistik simülasyonu |
| `customer-service` | `com.dgl.customer` | **8086** | `customer_db` (5432) | Müşteri profilleri, adresler, kullanıcı tercihleri |
| `notification-service` | `com.dgl.notification` | **8087** | `notification_db` (5432) | Olay dinleme, E-posta / SMS bildirim simülasyonu |

---

## 4. Kafka Konuları (Topics) ve İsimlendirme Standardı

Tüm Kafka konu isimleri nokta notasyonu ile `<domain>.<eylem>` şeklinde adlandırılır:

### Sipariş (Orders):
- `orders.created` - Sipariş oluşturuldu (Saga akışını başlatır: Stok rezervasyonu)
- `orders.confirmed` - Sipariş başarıyla tamamlandı (Tüm adımlar başarılı)
- `orders.cancelled` - Sipariş iptal edildi (Telafi / Compensation işlemlerini tetikler)

### Stok (Inventory):
- `inventory.reserved` - Stok başarıyla rezerve edildi
- `inventory.released` - Stok rezervasyonu serbest bırakıldı (İptal/Telafi durumu)
- `inventory.failed` - Yetersiz stok nedeniyle rezervasyon başarısız

### Ödeme (Payment):
- `payments.authorized` - Ödeme ön onayı alındı
- `payments.captured` - Ödeme hesaptan çekildi
- `payments.failed` - Ödeme reddedildi veya hata oluştu
- `payments.refunded` - Ödeme iade edildi (Telafi işlemi)

### Kargo (Shipping):
- `shipments.created` - Kargo kaydı oluşturuldu
- `shipments.cancelled` - Kargo iptal edildi (Telafi işlemi)
- `shipments.delivered` - Kargo teslim edildi

### Müşteri ve Sahtekarlık (Customer & Fraud):
- `customers.updated` - Müşteri bilgileri güncellendi
- `fraud.evaluated` - Sahtekarlık riski değerlendirildi (`ALLOW`, `REVIEW`, `BLOCK`)

### Hata Konuları (Dead Letter Topics - DLT):
- Her konunun zehirli mesajları için `.DLT` uzantılı bir hata konusu bulunur (örneğin: `orders.created.DLT`).

---

## 5. Teknoloji Yığını ve Kodlama Standartları

- **Dil ve Çalışma Zamanı**: Java 21 LTS (Modern özellikler aktif kullanılmalıdır: DTO ve Olaylar için `record`, Sealed sınıflar, Pattern Matching, Switch Expressions).
- **Çatı (Framework)**: Spring Boot 4.1.x, Spring Cloud 2025.x.
- **Kalıcılık**: Spring Data JPA, Hibernate, PostgreSQL.
- **Önbellek**: Redis (Spring Data Redis, Lettuce).
- **Mesajlaşma**: Spring for Apache Kafka.
- **Dayanıklılık (Resilience)**: Resilience4j (CircuitBreaker, Retry, TimeLimiter).
- **Model Tanımları**: Project Lombok (`@Getter`, `@Setter`, `@Builder`, `@RequiredArgsConstructor`).
- **Doğrulama (Validation)**: Jakarta Bean Validation (`@NotNull`, `@NotBlank`, `@Positive`, vb.).
- **Hata Formatı**: RFC 7807 `ProblemDetails` standartlarında `@RestControllerAdvice` ile global hata yönetimi.

### Standart Paket Yapısı (Her Servis İçin Geçerli)
Her mikroservis aşağıdaki temiz katmanlı mimariye sadık kalmalıdır:
```text
com.dgl.<service>
├── config/              # Güvenlik, Kafka, Redis, Web ve Swagger yapılandırmaları
├── controller/          # Dışa açılan REST Controller sınıfları
├── domain/              # Zengin Domain Modelleri (Entity, Value Object, Enum)
├── dto/                 # İstek ve Cevap DTO'ları (Java Record tercih edilir)
│   ├── request/
│   └── response/
├── exception/           # Özel Domain Hataları ve GlobalExceptionHandler
├── messaging/           # Kafka Üreticileri, Tüketicileri ve Olay Sınıfları
│   ├── event/           # Olay DTO'ları ve EventEnvelope
│   ├── producer/        # KafkaTemplate yayıncıları
│   └── consumer/        # @KafkaListener metotları
├── outbox/              # Outbox entity, repository ve zamanlanmış yayıncı
├── repository/           # Spring Data JPA Repository arayüzleri
└── service/             # Uygulama ve Domain İş Mantığı Servisleri
```

---

## 6. Derleme, Test ve Çalıştırma Yönergeleri

Her servis kendi bağımsız Maven sarmalayıcısına (`mvnw` / `mvnw.cmd`) sahiptir.

```powershell
# Tek bir servisi derlemek (örnek: order-service)
cd order-service
.\mvnw clean package -DskipTests
cd ..

# Bir servisin birim testlerini çalıştırmak
cd order-service
.\mvnw test
cd ..

# Bir servisi yerel ortamda başlatmak
cd order-service
.\mvnw spring-boot:run
cd ..
```

### Test İlkeleri
1. Domain modelleri ve servis katmanı JUnit 5 & Mockito ile test edilmelidir.
2. Repository katmanı Testcontainers (PostgreSQL) ile izole edilmelidir.
3. Mesajlaşma testlerinde `@EmbeddedKafka` veya Testcontainers Kafka kullanılmalıdır.
4. Saga akışlarında hem mutlu yol (happy path) hem de telafi yolları (compensating paths) test edilmelidir.

---

## 7. Git Commit Standartları ve Mesaj Formatı (Ayrıntılı ve Açıklayıcı)

Tüm commit mesajları Conventional Commits standardına uygun olmalı; soyut veya genel ifadeler yerine eklenen bileşenlerin adlarını ve sorumluluklarını açıkça içermelidir:

1. **DTO Commitleri**:
   - Asla sadece `feat(<servis>): add dtos` yazılmaz.
   - Hangi istek ve cevap DTO'larının eklendiği başlıkta ve gövdede listelenir.
   - Örnek Başlık: `feat(product): add product and category dtos (Create/UpdateProduct, ProductResponse, CategoryResponse)`

2. **Servis Katmanı Commitleri**:
   - Asla sadece `feat(<servis>): add service layer` yazılmaz.
   - Eklenen servis arayüzleri ve iş mantığı özellikleri listelenir.
   - Örnek Başlık: `feat(product): add service layer (ProductService, CategoryService with slug generation)`

3. **Entity ve Repository Commitleri**:
   - Eklenen aggregate, entity ve repository arayüzleri açıkça belirtilir.
   - Örnek Başlık: `feat(order): add domain entities (Order, OrderItem, OrderSagaState)`

---

## 8. Yapay Zeka Ajanları İçin Özel Yönergeler

Bu repoda geliştirme yaparken:
1. **Asla Monolit Kod Yazma**: Servis izolasyonunu koru. Bir servisin kodunu diğer servise asla import etme.
2. **Her Zaman Doğrulama ve İstisna Yönetimi Ekle**: Bean Validation kullan ve hatalarda `ProblemDetails` dön.
3. **Yinelenen Olayları Daima Yönet**: Kafka dinleyicilerine idempotent kontroller ekle.
4. **Saga Durum Makinesine Tam Uyum Sağla**: `order-service` içindeki ara durumları atlama.
5. **Açıklayıcı Git Commit Mesajları Kullan**: Commit atarken 7. bölümdeki ayrıntılı commit kurallarına harfiyen uy.
6. **Servise Özel Kuralları İncele**: Bir serviste kod yazmadan önce o servisin dizinindeki `AGENTS.md` ve `CLAUDE.md` dosyalarını mutlaka oku.
7. **İstisna Sınıflandırma Standardı (Retryable vs NonRetryable)**:
   - Yeni bir domain hatası eklerken mutlaka `BusinessRuleException` (ve dolayısıyla `NonRetryable`) veya `TransientException` (`Retryable`) türetilmelidir.
   - 4xx ve iş kuralı ihlalleri (`BusinessRuleException`) ASLA retry edilmez; doğrudan fail-fast veya Saga telafi akışına yönlendirilir.
   - Kafka tüketicilerinde `DefaultErrorHandler.addNotRetryableExceptions(...)` listesine kalıcı hatalar eklenmeli ve zehirli mesajlar gecikmeden `.DLT` kuyruğuna yönlendirilmelidir.
