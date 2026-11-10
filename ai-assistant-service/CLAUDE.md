# CLAUDE.md - AI Assistant Service

Tüm mimari kurallar, araç tanımları, güvenlik politikaları ve port dağılımları için lütfen [AGENTS.md](AGENTS.md) ve repo kökündeki [AGENTS.md](../../AGENTS.md) dosyalarını inceleyin.

### Hızlı Kurallar Özeti
- **Dil ve Sürüm**: Python 3.12+ (Astral `uv` ortam yöneticisi).
- **Kimlik Yönetimi**: Müşteri kimliği ASLA kullanıcı mesajından veya model promptundan kabul edilmez. Yalnızca `X-User-Id` başlığı (`RequestContext`) kullanılır. Araç parametre şemalarında `customer_id` bulunamaz (`extra="forbid"`).
- **Yazma İşlemleri**: LLM doğrudan iptal veya yazma işlemi yapamaz. Yalnızca `PendingAction` oluşturur; işlem kullanıcının `POST /agent/actions/{action_id}/confirm` onayıyla yürütülür.
- **Kargo İzolasyonu**: `shipping-service` doğrudan takip numarasıyla sorgulanamaz. Önce `order-service` sahiplik doğrulaması yapılır, ardından sipariş ID ile kargo bilgisi çekilir.
- **Terminal Politika**: Şirket politikası sorularında `search_policy` çıktısı modele yeniden yazdırılmaz; doğrulanmış atıflarıyla birlikte doğrudan kullanıcıya iletilir.
- **PII Hijyeni**: Adresler ve serbest kullanıcı metinleri dış LLM bağlamına veya loglara ham haliyle aktarılmaz.
- **Reranker Bayrağı**: `RAG_RERANK_ENABLED` varsayılan `False`'tur. Üretimde fail-open (`RAG_RERANK_FAIL_OPEN=True`), eval koşularında kesinlikle fail-closed çalışır.
- **Eureka REST ve Graceful Drain**: Eureka kaydı harici kütüphane yerine `httpx` tabanlı `app/discovery/` ile yönetilir; SIGTERM anında önce Eureka'dan deregister olur ve uçuştaki istekleri tamamlamak için 20 sn drain süresi bekler.
- **Zaman Aşımı Sıralaması ve Gateway Retry Yasağı**: Gateway seviyesinde AI rotalarında `Retry` filtresi KESİNLİKLE bulunmaz (çift token harcamasını ve aksiyon tekrarlarını önlemek için). Zaman aşımı hiyerarşisi: İstemci (~90s) > Gateway Read Timeout (80s) > Gateway TimeLimiter (70s/55s/20s/10s) > Python Tur Timeout (60s/45s) > Tekil LLM çağrısı (30s).
- **Ölçekleme ve Worker Kuralı**: Container başına kesinlikle tek bir Uvicorn worker'ı (`--workers 1`) çalışır. Ölçekleme container replikasyonu ile (`docker compose up --scale ai-assistant-service=N`) sağlanır.
- **Konfigürasyon İki Katman**: `Settings` (açılış/env) ve `RuntimeSettings` (Config Server/canlı).
- **Tur Başı Snapshot**: Endpoint'lerde `get_runtime_settings` ile tek snapshot alınır, servislere parametreyle (`limits`, `config`) geçirilir; tur ortasında config değişse bile devam eden istek etkilenmez.
- **Secret ve Prompt Yasağı**: Config Server'a secret veya prompt girmez; tavan değerler Gateway TimeLimiter'a (`agent <= 65s`, `rag <= 50s`) bağlıdır.
- **Önce Kod, Sonra Config**: Yeni bir runtime anahtarı eklerken `extra="forbid"` nedeniyle önce kod deploy edilir, sonra YAML güncellenir.
- **Kimlik ve Güven Modeli**: İki kimlik (kullanıcı: `X-User-Id`, servis: `X-Gateway-Secret`). Kimlik ASLA tool parametresi olamaz; `X-User-Roles` bilerek iletilmez. Yetki downstream'dedir, Python ikinci savunma hattıdır. Üretimde zayıf secret ile fail-fast (`startup_checks`).
- **Ayrık Audit**: `audit` logger (`propagate=False`, stdout JSON) PII içermez (`args_hash` + `arg_names`). `ToolResult.reason` modele yansımaz. Audit logları altyapıda ayrı index ve saklama süresiyle tutulmalıdır.
- **Yeni Tool Kontrolü**: `extra="forbid"`, kimlik parametresi yok, 403/404 aynı hata metni ("bulunamadı"), sahiplik uyuşmazlığında `reason="ownership_mismatch"`, `ToolRegistry` kaydı (otomatik audit), yan etkili işlemler yalnızca `PendingAction` teklifi üretir.
- **Gözlemlenebilirlik (Observability)**:
  - 3 ID Rolü: `Trace ID` (OTel W3C traceparent / Tempo), `Correlation ID` (RequestContext / Loki iş süreci), `Event ID` (Kafka envelope / idempotency).
  - Loglama: stdout tek satır JSON, Java MDC uyumlu anahtarlar (`traceId`, `spanId`, `correlationId`), formatter seviyesinde `mask_pii`.
  - Kafka Header: Her producer gönderimi `PRODUCER` span içine alınır ve `build_kafka_headers` ile `traceparent` ve `X-Correlation-Id` eklenir.
  - Metrikler ve Kardinalite: `http_server_requests_seconds` (route şablonu ile; ham URL/user_id label YASAKTIR), `ai_tool_call_duration_seconds` (bilinmeyen -> `unknown`), `ai_llm_request_duration_seconds`, `ai_llm_tokens_total`. `/actuator/prometheus` secret'sızdır.
  - Sağlık Probaları: `/actuator/health/liveness` (200), `/actuator/health/readiness` (startup+drain+redis). LLM veya downstream servisler KESİNLİKLE readiness'e eklenemez.
- **Birim Testleri**: Ağ veya Docker gerektirmeden `uv run pytest -m "not integration"` ile çalışır.
