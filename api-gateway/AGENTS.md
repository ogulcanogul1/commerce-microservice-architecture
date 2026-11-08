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

## 2. Temel Sorumluluklar ve Yönlendirme (Routing)

1. **Mikroservis Yönlendirmeleri**:
   - `/api/orders/**` -> `http://localhost:8082` (order-service)
   - `/api/products/**` -> `http://localhost:8081` (product-service)
   - `/api/customers/**` -> `http://localhost:8086` (customer-service)
   - `/api/payments/**` -> `http://localhost:8083` (payment-service)
   - `/api/inventory/**` -> `http://localhost:8084` (inventory-service)
   - `/api/shipping/**` -> `http://localhost:8085` (shipping-service)

2. **Ayrıştırılmış AI Asistanı Rotaları (`ai-assistant-service`)**:
   Tekil monolitik AI rotası yerine farklı gecikme ve risk profillerine sahip 4 bağımsız rota tanımlanmıştır:
   - `ai-actions-route` (`/agent/actions/**`, `/api/v1/chat/actions/**`): TimeLimiter 20s, Devre Kesici `aiActionsCircuitBreaker`, Fallback `/fallback/ai-actions` (`outcomeUnknown=true`, `retryable=false`).
   - `ai-chat-route` (`/agent`, `/agent/chat`, `/api/v1/chat`, `/api/v1/chat/chat`): TimeLimiter 70s, Devre Kesici `aiChatCircuitBreaker`, Fallback `/fallback/ai-chat`.
   - `ai-rag-answer-route` (`/rag/answer`): TimeLimiter 55s, Devre Kesici `aiRagAnswerCircuitBreaker`, Fallback `/fallback/ai-rag`.
   - `ai-rag-search-route` (`/rag/search`): TimeLimiter 10s, Devre Kesici `aiRagSearchCircuitBreaker`, Fallback `/fallback/ai-rag`.
   - **KURAL (KESİNLİKLE RETRY YOK):** AI rotalarında Gateway seviyesinde `Retry` filtresi **asla** bulunmaz. Zaman aşımı veya arıza durumunda istek tekrar edilmez; çünkü ilk denemede yan etkili araçlar (iptal vb.) çalışmış veya LLM token faturası üretilmiş olabilir.

3. **İstek Gövdesi Sınırı (`AiRequestSizeFilter`)**:
   - AI uç noktalarına (`POST` istekleri) 64 KB (65.536 bayt) üst sınır uygulanır.
   - Sınır aşıldığında gövde arka uca aktarılmadan `413 Payload Too Large` standart RFC 7807 `ProblemDetail` cevabı dönülür.

4. **Rota Bazlı Hız Sınırı (Rate Limiting) ve Kayan Pencere**:
   - Genel rotalar için sabit pencere (Fixed Window) kullanılır.
   - AI rotaları için **Kayan Pencere (Sliding Window Counter)** Lua betiği çalışır; pencere sınırlarındaki 2× ani yük patlamaları (burst) ağırlıklı hareketli ortalama ile engellenir.
   - **Kova İzolasyonu:** Her politikanın kendi kova anahtarı vardır (`ai-actions:user:123`, `ai-chat:user:123` vb.). Ürün gezen kullanıcı AI kotasını tüketmez.
   - **Arıza Modu (Fail-Mode: LOCAL):** Redis kesintisinde genel rotalar `fail-open` olurken, AI rotaları kontrolsüz maliyet artışını önlemek için süreç içi `LocalSlidingWindowLimiter` bellek içi sınırlayıcısına geçer.
   - **IP Sahteciliği Koruması:** `trust-forwarded-for: false` yapılandırmasıyla `X-Forwarded-For` başlığına güvenilmez, kesin olarak `request.getRemoteAddr()` kullanılır.

5. **İzleme ve Bağlam Taşıma (Correlation ID)**:
   - Her gelen istekte `X-Correlation-Id` kontrol edilir; yoksa yeni `UUIDv4` üretilerek downstream servislere ve yanıt başlıklarına aktarılır.

6. **Kimlik Doğrulama ve Güvenlik (JWT)**:
   - Genel uç noktalar (ör. `GET /api/v1/products/**`) hariç tüm isteklerde `Authorization: Bearer <jwt>` doğrulanır.
   - Doğrulanmış kullanıcı ID'si `X-User-Id` başlığıyla downstream servislere taşınır.

---

## 3. Kod ve Paket Yapısı

```text
com.dgl.gateway
├── config/              # SecurityFilterChain, Gateway Route ve Resilience yapılandırmaları
├── controller/          # FallbackController (Devre kesici devreye girdiğinde dönen RFC 7807 yanıtları)
├── filter/              # CorrelationIdFilter, JwtAuthenticationFilter, AiRequestSizeFilter, RateLimitingFilter
├── ratelimit/           # RateLimiterService (Lua), LocalSlidingWindowLimiter, RateLimitPolicy, RateLimitProperties
└── security/            # JwtValidator
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
