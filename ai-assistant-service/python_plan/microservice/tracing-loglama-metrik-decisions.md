# Tracing, Loglama ve Metrik Entegrasyonu Karar Günlüğü

Plan: `tracing-loglama-metrik-entegrasyonu.md`. Her adımda yaptığın sapmayı, çıkan sürprizi ve doğrulanamayan şeyi buraya ekle.

## 1. Baseline
- Python (`uv run pytest -m "not integration" -q`): 732 passed, 1 skipped, 7 deselected
- Tarih: 2026-11-10

## 2. Plan öncesi verilen kararlar
- **Alan adları Java MDC ile aynı:** JSON logda `traceId`, `spanId`, `correlationId` (ECS `trace.id` DEĞİL). Sebep: Java servisleri bu repoda ECS JSON değil düz metin pattern basıyor (`[app,traceId,spanId,correlationId]`), Promtail bu anahtarlara göre çalışıyor.
- **PII:** nottaki ham regex yerine mevcut `app/core/pii.py::mask_pii` kullanılır (TCKN/Luhn doğrulamalı, daha az yanlış pozitif).
- **Kafka'da `traceparent` yalnızca header'da**, event envelope gövdesi değişmez. `X-Correlation-Id` header'ı da eklenir (Java `OutboxPoller` ile aynı sözleşme). Baggage taşınmaz.
- **Yalnızca traces OTLP ile gider;** metrik Prometheus pull, log stdout→Promtail. OTel metrics/logs SDK kapsam dışı.
- **Sampling:** `ParentBased(ALWAYS_ON)`, gateway'in kararına uyar.
- **`/actuator/prometheus` ve probe endpoint'leri secret'sız**, `/actuator/refresh` secret'lı kalır. Gerekçe: Prometheus v2.51 özel header gönderemez; Java servislerinde de `/actuator/**` muaf; port yayımlı değil. Gateway'in bu yolu iletmediği Adım 12'de doğrulanır.
- **`application` label'ı yalnızca scrape job'ında**, kodda yok (`exported_application` çakışmasını önlemek için).
- **Readiness bilerek yalnızca: startup + drain + (varsa) Redis.** LLM, downstream servisler, Qdrant, Kafka yok. Kafka producer lazy başlıyor, açılışta kontrol yanlış alarm üretirdi.
- **Kapsam dışı (ertelendi):** Java log JSON'a geçişi, exemplar, tail sampling, Loki/Grafana alarm kuralları, Python Kafka consumer, çok-process metrik birleştirme.

## 3. Nottaki hatalar (repo ile çelişen iddialar)
- `telemetry.py` yok, Python serviste hiç OpenTelemetry yok (not "HTTP tarafı tamam" diyor).
- `KafkaEscalationProducer` değil `KafkaTicketPublisher`; hiç header göndermiyor (not X-Correlation-Id yazıyor sanıyor).
- `PIIMasker` sınıfı değil `mask_pii` fonksiyonu.
- `/actuator/health` yok; `/health` var.
- Java loglar ECS JSON değil.

## 4. Adım notları
- **Adım 1:** Bağımlılıklar eklendi, OTEL ve LOG ayarları tanımlandı. Baseline korundu.
- **Adım 2:** Tracing kuruldu (OTLP, FastAPI, HTTPX). Testler izole InMemory exporter ile yazıldı.
- **Adım 3:** Correlation ID ContextVar ve saf ASGI RequestContextMiddleware eklendi. CRLF ve asenkron yayılım testleri yeşil.
- **Adım 4 (L1 Doğrulaması):** `import logging, app.main; logging.getLogger('app.x').info('...')` çalıştırıldığında konsola HİÇBİR çıktı basılmadığı görüldü (L1 riski doğrulandı: root logger'da stdout handler yok, dolayısıyla uvicorn dışındaki uygulama logları sessizce kayboluyor). `configure_logging()` ile bu sorun çözüldü.
- **Adım 5:** `write_audit` kaydına aktif span geçerli olduğunda `traceId` enjeksiyonu eklendi.
- **Adım 6:** KafkaTicketPublisher.publish PRODUCER span içine alındı, build_kafka_headers ile traceparent ve X-Correlation-Id başlıkları eklendi.
- **Adım 7:** Prometheus metrikleri (http_server_requests_seconds, ai_tool_call_duration_seconds, ai_llm_request_duration_seconds, ai_llm_tokens_total) ve HttpMetricsMiddleware tamamlandı.
- **Adım 8:** /actuator/prometheus, /actuator/health/liveness ve /actuator/health/readiness açıldı. Readiness'e LLM ve downstream servislerin konulmaması ilkesi korundu. SIGTERM yakalandığında hazır olmama durumunu bildirmek için `app/discovery/drain.py` içine `is_draining()` kontrolü eklendi. Redis açılışta bağlanamayıp InMemoryBudgetStore deposuna düştüğünde servisi kalıcı 503 OUT_OF_SERVICE kilitlenmesinden korumak için `redis: DISABLED` dönmesi sağlandı.
- **Adım 9:** Birleşik doğrulama: 759 passed, 1 skipped, 7 deselected (baseline 732'den +27 yeni test). Python adımları tamamlandı.
- **Adım 10:** `docker/monitoring/prometheus/prometheus.yml` içine `ai-assistant-service:8089` scrape job'ı eklendi. Ağ teyidi yapıldı: `docker-compose.yml` (Prometheus) ile `docker-compose.apps.yml` (`ai-assistant-service`) her ikisi de harici/ortak `commerce-network` köprü ağını kullanmaktadır. Bu sayede host portu açmaya gerek kalmadan servis adı üzerinden doğrudan 8089 portuna erişim sağlanmaktadır.
- **Adım 11:** `docker-compose.apps.yml` içinde `ai-assistant-service` ortam değişkenlerine `LOG_FORMAT=json` eklendi. `docker/monitoring/promtail/promtail.yml` pipeline_stages kısmına Docker JSON sarmalayıcı ve kaçış karakterleriyle uyumlu `{job="docker-containers"} |~ "ai-assistant-service"` filtreli JSON stage eklendi. `JsonLogFormatter` için `separators=(",", ":")` ve `stack_info` desteği eklendi.
- **Adım 12:** `ai-assistant-service/AGENTS.md` ve `CLAUDE.md` belgelerine "Gözlemlenebilirlik (Observability)" kılavuzu eklendi (Trace Context, MDC alanları, metrik label kuralları, Kafka başlık kontrol listesi, readiness izolasyon kuralları ve run_in_executor yasağı).
- **Ek İyileştirmeler (Code Polish & Robustness):**
  - `AgentService.chat` metriklerinde `provider` label'ı kardinalite riskini önlemek için tek bir kaynağa (`BaseLLMProvider.provider`) bağlandı ve `isinstance(..., str)` denetimiyle güvene alındı.
  - `app/agent/tickets.py` ve `app/agent/service.py` import dizilimleri PEP 8 standardına göre (3rd-party OpenTelemetry önce, first-party app.* sonra) düzenlendi.
  - `docker/monitoring/prometheus/prometheus.yml` dosya sonundaki fazla boşluk temizlendi.
  - Nihai test paketi çalıştırıldı: 760 passed, 8 skipped, 0 failed.

## 5. Doğrulanamayanlar
Docker kümesi (tüm microservice ve monitoring stack'i) bu geliştirme oturumunda yerel makinede ayağa kaldırılmadığı için Adım 12.2 kapsamındaki canlı sistem doğrulamaları yapılamamıştır:
1. **Canlı Prometheus Scrape UI:** Prometheus web arayüzünde (port 9090) Status -> Targets altında `ai-assistant-service` hedefinin canlı UP durumu ve `/actuator/prometheus` scrape döngüsü.
2. **Canlı Tempo / Grafana Dağıtık Trace Grafiği:** `api-gateway` -> `ai-assistant-service` -> `order-service` / `shipping-service` ve `KafkaTicketPublisher` -> `notification-service` trace yayılımının Tempo UI (port 3200 / Grafana port 3000) üzerinden canlı görselleştirilmesi.
3. **Canlı Loki / Promtail Log Akışı:** Docker container stdout'undan Promtail aracılığıyla Loki'ye akan loglarda `{app="ai-assistant-service"} | json | correlationId="..."` filtrelemesinin canlı Grafana Explore panelinde teyidi.
4. **API Gateway Actuator Filtresi:** API Gateway'in dış dünyadan gelen `/actuator/**` isteklerini `ai-assistant-service`'e iletmediğinin canlı HTTP isteğiyle doğrulanması (Birim testlerinde `/actuator/prometheus` ve `/actuator/health/*` rotalarının secret'sız çalıştığı, `/actuator/refresh` rotasının ise secret korumasını sürdürdüğü doğrulanmıştır).
5. **Grafana AI Service Dashboard Row:** Canlı veriler ve metrik serileri olmadan panoyu bozmamak adına Grafana JSON panosuna yeni satır eklenmesi ertelenmiştir.
