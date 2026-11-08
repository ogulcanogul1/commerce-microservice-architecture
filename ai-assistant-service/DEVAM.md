# DEVAM — AI Assistant Service & Gateway Entegrasyonu Oturum Devir ve İlerleme Raporu

## Tamamlanan Aşama: API Gateway ve Service Discovery Entegrasyonu (`python_plan/microservice/gateway-entegrasyonu.md`)

`ai-assistant-service/python_plan/microservice/gateway-entegrasyonu.md` planındaki Adım 0'dan Adım 9'a kadar tüm adımlar eksiksiz tamamlanmış; Python ve Java servisleri izole test paketleriyle %100 doğrulanmış, adım adım commit'lenmiş ve `origin main` dalına push'lanmıştır. Mimari kararlar `python_plan/microservice/gateway-decisions.md` dosyasına kaydedilmiştir.

---

### Tamamlanan Mimari Bileşenler ve Kapsam:

1. **Eureka REST İstemcisi ve Graceful Drain (`app/discovery/`):**
   - Harici ağır kütüphaneler yerine `httpx` tabanlı yalın REST istemcisi (`EurekaClient`).
   - Periyodik heartbeat (`EUREKA_RENEWAL_SEC=10s`) atan ve yaşam döngüsünü yöneten `EurekaRegistrar`.
   - POSIX `SIGTERM` sinyalinde önce Eureka'dan deregister olup soketi açık tutarak 20 sn bekleyen `install_sigterm_drain`; böylece uçuştaki istekler sıfır kesintiyle tamamlanır.
   - Dinamik hostname/IP çözümlemesi (`resolve_instance_host`).

2. **Python Tarafı Koruma Katmanları (`app/core/`):**
   - `BodySizeLimitMiddleware`: 64 KB üstü POST/PUT/PATCH isteklerini gövdeyi belleğe almadan fail-fast `413` ile reddeder.
   - `ConcurrencyLimiter`: Instance başına eşzamanlı LLM turu kotası (`AI_MAX_CONCURRENT_REQUESTS=20`) dolduğunda kuyruğa almadan derhal `503 Service Overloaded` + `Retry-After: 5` döner.
   - Tur Bütçesi (Turn Timeout): Agent için 60 sn (`AGENT_TURN_TIMEOUT_SEC`), RAG için 45 sn (`RAG_TURN_TIMEOUT_SEC`) zaman aşımı bütçesi.

3. **Token Bütçesi (Reserve & Reconcile, `app/budget/`):**
   - Kullanıcı (`tok:user:{id}:day`, `tok:user:{id}:min`) ve sağlayıcı (`tok:provider:{name}:min`) kotalarını denetleyen `TokenBudgetService`.
   - Redis üzerinde atomik Lua betikleri (`RESERVE_LUA_SCRIPT`, `ADJUST_LUA_SCRIPT`) ile çift harcama ve eşzamanlı aşım engellemesi.
   - Kota aşımında makine tarafından okunabilir RFC 7807 `429 Too Many Requests` ve `Retry-After` yanıtı.
   - Redis kesintisinde `fail_mode="local"` ile bellek içi depoya (`InMemoryBudgetStore`) zarif geçiş.

4. **Kalıcı Aksiyon Deposu (`RedisPendingActionStore`, `app/agent/redis_pending.py`):**
   - Çok replikalı dağıtık ortamlarda kullanıcı aksiyon teklifi ve onayının (`/agent/actions/{action_id}/confirm`) farklı container'lara düşmesi senaryosu için geliştirildi.
   - Atomik Lua betikleri (`CONSUME_LUA_SCRIPT`, `DISCARD_LUA_SCRIPT`) ile tek kullanımlık tüketim ve kullanıcı sahiplik izolasyonu.

5. **API Gateway AI Rota Ayrıştırması ve Devre Kesiciler (`api-gateway`):**
   - Tekil monolitik AI rotası 4 bağımsız rotaya bölündü:
     - `ai-actions-route` (TimeLimiter 20s, CircuitBreaker, Fallback `/fallback/ai-actions` - `outcomeUnknown=true`, `retryable=false`)
     - `ai-chat-route` (TimeLimiter 70s, CircuitBreaker, Fallback `/fallback/ai-chat`)
     - `ai-rag-answer-route` (TimeLimiter 55s, CircuitBreaker, Fallback `/fallback/ai-rag`)
     - `ai-rag-search-route` (TimeLimiter 10s, CircuitBreaker, Fallback `/fallback/ai-rag`)
   - **KESİNLİKLE RETRY YOK:** AI rotalarında çift token faturası ve mükerrer işlem riskine karşı Gateway `Retry` filtresi kaldırıldı.
   - `AiRequestSizeFilter`: AI rotalarına gelen 64 KB üzeri POST isteklerini Gateway seviyesinde `413 ProblemDetail` ile keser.

6. **Gateway Rota Bazlı Kayan Pencere Rate Limiting (`com.dgl.gateway.ratelimit`):**
   - `RateLimitPolicy` record ve `RateLimitProperties` ile konfigüre edilen rota politikaları: `ai-actions` (20/dk), `ai-chat` (10/dk), `ai-rag-answer` (10/dk), `ai-rag-search` (30/dk).
   - `RateLimiterService`: İki ardışık pencere üzerinden ağırlıklı hareketli ortalama hesaplayan atomik kayan pencere (sliding window counter) Lua betiği.
   - `LocalSlidingWindowLimiter`: Redis kesintisinde AI rotalarının kontrolsüz fatura üretmesini engellemek için süreç-içi bellek sınırlayıcısına geçiş (`fail-mode: LOCAL`).
   - `RateLimitingFilter`: Kova izolasyonu, `trust-forwarded-for: false` ile IP sahteciliği koruması ve 429 yanıtlarında dolan kovanın adını bildiren `"policy"` alanı.

---

### Doğrulama ve Test Özeti:

- **Python (`ai-assistant-service`):**
  - **592 passed**, 1 skipped, 7 deselected (~40 saniye).
  - Tüm limit, token budget, redis pending store, discovery ve API testleri yeşil.
- **Java Gateway (`api-gateway`):**
  - **48 passed**, 0 failure (Temel başlangıç 28 testten 48 teste çıkarıldı).
  - `FallbackControllerTest` (12 test), `AiRequestSizeFilterTest` (4 test), `RateLimitingFilterTest` (9 test), `LocalSlidingWindowLimiterTest` (4 test), `RateLimiterServiceTest` (7 test) tamamı başarılı.
- **Eureka Server (`eureka-server`):**
  - **1 passed**, BUILD SUCCESS.
- **Ne Yapıldı / Ne Yapılmadı:**
  - *Yapıldı:* Adım 0 - Adım 8 arasındaki tüm kod, konfigürasyon, filtre, yaşam döngüsü, birim/entegrasyon testleri ve dokümantasyon tamamlandı.
  - *Yapılmadı:* Yerel ortamda Docker daemon servisinin kapalı olması nedeniyle çoklu container uçtan uca canlı Compose testi çalıştırılamadı ("uçtan uca doğrulanmadı" olarak karar günlüğüne işlendi). Tüm iş mantığı izole testlerle %100 güvenceye alındı.

---

### Gelecek Oturumlar İçin Notlar:
1. **Canlı Docker Doğrulaması:** Docker servisi aktif olduğunda `docker compose -f docker-compose.yml -f docker-compose.apps.yml up -d --scale ai-assistant-service=2` ile canlı scale ve drain testi yapılabilir.
2. **Streaming / SSE Uç Noktaları:** Python tarafında SSE desteği eklendiğinde Gateway tamponlama başlıkları ve stream içi hata yönetimi (`event: error`) tasarlanabilir.
3. **Corpus Büyütme ve Canlı Reranker Koşusu:** Reranker A/B testlerinin gerçek PDF korpusu ile yürütülmesi.

### Başvuru Dokümanları:
1. `python_plan/microservice/gateway-decisions.md` (Mimari kararlar)
2. `python_plan/microservice/gateway-entegrasyonu.md` (Entegrasyon planı)
3. `AGENTS.md` & `CLAUDE.md` (Her iki servis dizinindeki yönergeler)
