# CLAUDE.md - API Gateway Servisi Rehberi

Bu servis `api-gateway` modülü olup dış dünyadan gelen isteklerin yönlendirilmesi, güvenlik kontrolleri, hız sınırları ve dayanıklılık mekanizmalarından sorumludur.

Detaylı teknik mimari ve kurallar için [AGENTS.md](AGENTS.md) ve kök dizindeki [AGENTS.md](../AGENTS.md) dosyalarına bakın.

### Hızlı Başvuru
- **Port**: `8080`
- **Ana Roller**: Reverse Proxy, JWT Doğrulama, Dağıtık Redis Rate Limiter, Resilience4j Circuit Breaker, `X-Correlation-Id` taşıma.
- **Ayrıştırılmış AI Rotaları**: `ai-actions-route` (20s), `ai-chat-route` (70s), `ai-rag-answer-route` (55s), `ai-rag-search-route` (10s).
- **AI Rotalarında Kesin Kural**: AI rotalarında Gateway seviyesinde `Retry` filtresi KESİNLİKLE bulunmaz (mükerrer token faturası ve çift aksiyon riski).
- **Hız Sınırı (Rate Limiting)**: AI rotaları kayan pencere (sliding window Lua) ve kova izolasyonu (`ai-chat`, `ai-actions` vb.) kullanır; Redis arızasında `fail-mode: LOCAL` bellek içi sınırlayıcıya geçer.
- **Yük Limiti**: AI POST isteklerine `AiRequestSizeFilter` ile 64 KB üst sınır uygulanır (aşımda 413).
- **Komutlar**:
  - Derleme: `cd api-gateway; .\mvnw clean compile; cd ..`
  - Test: `cd api-gateway; .\mvnw test; cd ..`
  - Çalıştırma: `cd api-gateway; .\mvnw spring-boot:run; cd ..`
