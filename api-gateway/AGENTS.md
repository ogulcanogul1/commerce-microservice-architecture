# API Gateway Servisi - Geliştirme Yönergeleri (AGENTS.md)

> Bu belge, `api-gateway` servisi için geçerli olan mimari kararları, yapılandırmaları ve kuralları tanımlar.

---

## 1. Servis Genel Bakışı
- **Dizin**: `api-gateway`
- **Paket**: `com.dgl.gateway`
- **Varsayılan Port**: `8080`
- **Bağımlılıklar**: Spring Cloud Gateway Server (WebMVC), Spring Security, Resilience4j, Redis, Actuator

API Gateway, platformun dış dünyaya açılan tek giriş kapısıdır. İstemci isteklerini yönlendirir, kimlik doğrular, hız sınırları (rate limiting) uygular ve devre kesiciler (circuit breaker) ile arka uç servislerini korur.

---

## 2. Temel Sorumluluklar

1. **Dinamik Yönlendirme (Routing)**:
   - `/api/orders/**` -> `http://localhost:8082` (order-service)
   - `/api/products/**` -> `http://localhost:8081` (product-service)
   - `/api/customers/**` -> `http://localhost:8086` (customer-service)
   - `/api/payments/**` -> `http://localhost:8083` (payment-service)
   - `/api/inventory/**` -> `http://localhost:8084` (inventory-service)
   - `/api/shipping/**` -> `http://localhost:8085` (shipping-service)

2. **İzleme ve Bağlam Taşıma (Correlation ID)**:
   - Her gelen istekte `X-Correlation-Id` başlığı kontrol edilir. Yoksa yeni bir `UUIDv4` üretilir.
   - Bu başlık, yönlendirilen alt servislere kesintisiz iletilir ve HTTP yanıt başlıklarına eklenir.

3. **Hız Sınırlandırması (Rate Limiting)**:
   - Redis tabanlı Token Bucket algoritması kullanılır.
   - İstemci IP'si veya kimliği doğrulanmış kullanıcı kimliği (User ID / API Key) bazında sınırlandırma yapılır.
   - Limit aşıldığında `429 Too Many Requests` ve standart `ProblemDetails` cevabı dönülür.

4. **Dayanıklılık ve Devre Kesici (Resilience4j Circuit Breaker)**:
   - Aşağı akış (downstream) servis çağrıları CircuitBreaker ve TimeLimiter ile korunur.
   - Servis yanıt vermediğinde veya hata eşiği aşıldığında tanımlı Fallback denetleyicisine (`/fallback/**`) yönlendirilir.

5. **Kimlik Doğrulama ve Yetkilendirme (Security)**:
   - JWT / OAuth2 Resource Server doğrulaması.
   - Genel uç noktalar (örneğin ürün kataloğu okuma: `GET /api/products/**`) halka açık, sipariş ve ödeme uç noktaları ise kimlik doğrulaması gerektirir.

---

## 3. Kod ve Paket Yapısı

```text
com.dgl.gateway
├── config/              # SecurityFilterChain, Gateway Route yapılandırmaları
├── filter/              # CorrelationIdFilter, LoggingFilter, RateLimitingFilter
└── controller/          # FallbackController (Devre kesici devreye girdiğinde dönen yanıtlar)
```

---

## 4. Geliştirme ve Test Komutları

```powershell
cd api-gateway
.\mvnw clean compile
.\mvnw test
.\mvnw spring-boot:run
cd ..
```
