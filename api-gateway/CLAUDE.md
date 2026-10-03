# CLAUDE.md - API Gateway Servisi Rehberi

Bu servis `api-gateway` modülü olup dış dünyadan gelen isteklerin yönlendirilmesi, güvenlik kontrolleri, hız sınırları ve dayanıklılık mekanizmalarından sorumludur.

Detaylı teknik mimari ve kurallar için [AGENTS.md](file:///D:/backend_projects/commerce/api-gateway/AGENTS.md) ve kök dizindeki [AGENTS.md](file:///D:/backend_projects/commerce/AGENTS.md) dosyalarına bakın.

### Hızlı Başvuru
- **Port**: `8080`
- **Ana Roller**: Reverse Proxy, JWT Doğrulama, Redis Rate Limiter, Resilience4j Circuit Breaker, `X-Correlation-Id` taşıma.
- **Komutlar**:
  - Derleme: `cd api-gateway; .\mvnw clean compile; cd ..`
  - Test: `cd api-gateway; .\mvnw test; cd ..`
  - Çalıştırma: `cd api-gateway; .\mvnw spring-boot:run; cd ..`
