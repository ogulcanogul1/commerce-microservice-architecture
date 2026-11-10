# AI Assistant Service - Mimari ve Mühendislik Kuralları (AGENTS.md)

## 1. Servis Rolü ve Sorumlulukları
- **Servis Adı:** `ai-assistant-service`
- **Teknoloji Yığını:** Python 3.12+, FastAPI, Astral `uv`, OpenTelemetry, Redis, `aiokafka`, `httpx` (Eureka REST istemcisi, `app/discovery/`).
- **Varsayılan Port:** `8089` (Debezium Kafka Connect `8088` ile çakışmaması için).
- **Veritabanı Kuralı (Non-Negotiable):** Bu servis **KESİNLİKLE** diğer mikroservislerin PostgreSQL veritabanlarına doğrudan bağlanamaz. Tüm veri okuma/yazma işlemleri HTTP (`order-service`, `product-service`, `shipping-service`, `inventory-service`) ve Apache Kafka (`support.ticket.created`) üzerinden gerçekleştirilir.
- **Worker ve Ölçekleme Kuralı:** Container/Process başına KESİNLİKLE tek bir Uvicorn worker'ı (`--workers 1`) çalışır (birden fazla worker aynı `instanceId` ile Eureka kaydını ezer ve heartbeat'leri bozar). Ölçekleme container replikasyonu ile (`docker compose up --scale ai-assistant-service=N`) sağlanır.

## 2. Güvenlik, İzleme ve Hız/Bütçe Kuralları
- **Gateway Bypass Koruması:** `/actuator/**`, `/health` ve `/docs` dışındaki tüm uç noktalar `X-Gateway-Secret` başlığını doğrular.
- **IDOR Koruması:** Ajan tool fonksiyonları müşteri kimliğini kullanıcı prompt'undan değil, API Gateway'in doğruladığı `X-User-Id` başlığından (`RequestContext`) alır. `customer_id` asla araç parametre şemasına eklenemez (`extra="forbid"`).
- **PII Maskeleme:** Kredi kartı, TCKN gibi hassas veriler dış LLM sağlayıcılarına gönderilmeden önce maskelenir. Adres ve alıcı adı gibi PII alanları downstream modellerden LLM context'ine aktarılmaz.
- **Standart Olay Zarfı:** Kafka'ya basılan tüm olaylar (`support.ticket.created`) platformun standart `EventEnvelope` şemasına (`eventId`, `eventType`, `aggregateId`, `aggregateType`, `timestamp`, `version`, `correlationId`, `causationId`, `payload`) uymak zorundadır.
- **Hız Sınırı ve Token Bütçesi Ayrımı:** Gateway istek adedini (DDoS/kötüye kullanım), Python `TokenBudgetService` ise kullanıcı/sağlayıcı token tüketimini (maliyet koruması) sınırlar. Token bütçesi reserve-and-reconcile deseniyle Redis üzerinde atomik Lua betikleriyle işletilir. Bütçe aşımında 429 `ProblemDetail` ve `Retry-After` dönülür.

## 3. Dağıtık Sistem Dayanıklılığı ve Gateway Entegrasyonu
- **Eureka Service Discovery ve Graceful Drain:** Eureka kaydı ve heartbeat işlemleri harici kütüphane yerine `httpx` tabanlı `app/discovery/` ile yürütülür. SIGTERM sinyalinde önce Eureka'dan deregister olunur ve soket açık tutularak 20 sn drain süresi beklenir; böylece uçuştaki istekler sıfır kesintiyle tamamlanır.
- **Gateway Retry Yasağı:** Gateway seviyesinde AI rotalarında `Retry` filtresi KESİNLİKLE bulunmaz (mükerrer token faturası ve çift aksiyon yürütme riski).
- **Zaman Aşımı (Timeout) Hiyerarşisi:** Dış katman süresi iç katmandan daima uzundur:
  `İstemci (~90s) > Gateway Read Timeout (80s) > Gateway TimeLimiter (70s/55s/20s/10s) > Python Tur Timeout (60s/45s) > Tekil LLM çağrısı (30s) > Tool çağrısı (5s)`.
- **Kalıcı Aksiyon Deposu (`RedisPendingActionStore`):** Çoklu replika ortamlarında onay isteklerinin (`/agent/actions/{action_id}/confirm`) farklı container'a düşmesi durumunda aksiyon kaybı yaşanmaması için aksiyonlar Redis üzerinde atomik Lua betikleriyle yönetilir.

## 4. Müşteri Destek Ajanı Kuralları (Customer Support Agent)
- **Onaylı Aksiyon Modeli (Human-in-the-Loop):** Model doğrudan veritabanında veya sipariş üzerinde değişiklik (iptal vb.) yapamaz. Yalnızca `PendingAction` önerisi oluşturabilir. İşlem yalnızca kullanıcının `POST /agent/actions/{action_id}/confirm` çağrısıyla gerçekleşir.
- **Sahiplik Doğrulaması (Kargo):** Kargo sorguları asla doğrudan kargo takip numarası ile yapılamaz; önce sipariş sahipliği `order-service` üzerinden doğrulanır, ardından sipariş ID ile kargo servisi çağrılır.
- **Terminal Politika Kuralı:** İade, kargo, garanti gibi şirket politikası sorularında `search_policy` çağrıldığında RAG cevabı modele özetletilmeden atıflarıyla birlikte doğrudan kullanıcıya döndürülür.
- **Grounding Kuralı:** Asistan, araç çağırmadan sayısal bilgi veremez veya araç çıktısında yer almayan uydurma rakamlar üretemez. İhlal durumunda 1 düzeltme hakkı tanınır, aksi halde güvenli fallback mesajı dönülür.
- **Log Hijyeni:** Loglarda ham `user_id` (yerine SHA-256 hash'i kullanılır), serbest kullanıcı mesajı ve sipariş tutarları asla yer alamaz.

## 5. Reranker ve İki Aşamalı Arama Kuralları
- **Opsiyonellik ve Bayrak Koruması:** Reranker `RAG_RERANK_ENABLED=False` (varsayılan) ile tamamen izoledir. Bayrak kapalıyken çalışma zamanı ek gecikmesi ve ağır bağımlılık importu yapılmaz.
- **Fail-Open vs Fail-Closed:** Üretim ortamında reranker arızası veya zaman aşımı kullanıcı deneyimini bozamaz (`RAG_RERANK_FAIL_OPEN=True` ile ilk $k$ hibrit sonuca dönülür). Değerlendirme (eval) ve test modlarında ise sessiz kalite bozulmalarını gizlememek için kesinlikle fail-closed çalışır (`fail_open=False`).
- **Abstain Gate İzolasyonu:** `RAG_MIN_DENSE_SCORE` doğrudan dense arama benzerlik skoruna bakar. Reranker skorları modeller arasında farklı ölçeklerde (logit, olasılık vb.) olduğu için çekinme (abstain) karar mekanizmasına karıştırılamaz.
- **Güvenlik ve Gizlilik:** Cohere veya dış reranker sağlayıcılarının API anahtarları asla loglanamaz veya hata mesajlarında sızdırılamaz.


## 6. Konfigürasyon Mimarisi (Spring Cloud Config & Runtime Ayarları)
- **İki Katmanlı Yapı:**
  1. `Settings` (`app/core/config.py`): Yalnızca açılışta ortam değişkenlerinden (`.env`) okunan, container restart gerektiren sabit ayarlar (bağlantı havuzları, secret'lar, portlar, API anahtarları).
  2. `RuntimeSettings` (`app/runtimeconfig/`): Spring Cloud Config Server üzerinden açılışta yüklenen ve çalışma zamanında kesintisiz (`POST /actuator/refresh`) güncellenebilen dinamik ayarlar (agent adımları, timeout bütçeleri, log seviyesi, bütçe kotaları).
- **Canlı Konfigürasyon Kuralları:**
  1. **Gizli Bilgi ve Prompt Yasağı:** Secret, şifre, API anahtarı veya sistem promptları asla Config Server'a veya `RuntimeSettings`'e konulamaz.
  2. **İstek Başına Snapshot:** Tüm servis ve endpoint'ler konfigürasyonu doğrudan `RuntimeConfigHolder.current` üzerinden serbestçe okuyamaz. `get_runtime_settings(request)` dependency'si üzerinden her turun başında değiştirilemez (frozen) bir snapshot alınır ve fonksiyonlara parametre olarak (`limits=runtime.agent`, `config=gen_config`) aktarılır. Tur ortasında refresh çağrılsa bile devam eden turun kuralları bozulmaz.
  3. **Gateway Invariant Tavanları:** Python tur zaman aşımı bütçeleri API Gateway TimeLimiter tavanlarını aşamaz (`agent.turn_timeout_sec <= 65.0`, `rag.turn_timeout_sec <= 50.0`). Bu tavanları aşan Config Server değerleri Pydantic doğrulamasıyla reddedilir ve eski geçerli konfigürasyon korunur.
  4. **Şema Genişletme Sırası:** Config Server'a yeni bir anahtar ekleneceği zaman, `extra="forbid"` kuralı nedeniyle **önce Python kodu deploy edilir, ardından Config Server YAML dosyası güncellenir**. Aksi takdirde eski kod bilinmeyen anahtarı reddeder.
  5. **Yenileme ve Ağ Modeli (Bilinen Sınırlama):** Arka planda polling döngüsü bulunmaz; açılışta Config Server kapalıysa servis env fallback ile çalışır ve sonradan elle `POST /actuator/refresh` çağrılana kadar yerel ayarlarda kalır. `/actuator/**` uç noktaları Gateway arkasında değildir, yalnızca Docker dahili ağı içinden erişilebilir; eşzamanlı çağrılar `asyncio.Lock` ile korunur.

## 7. Kimlik ve Güven Modeli (Identity & Trust Hardening)
- **İki Kimlik Katmanı:** İsteklerde kullanıcı kimliği `X-User-Id` (`RequestContext`), servis güvenliği ise Gateway ile paylaşılan `X-Gateway-Secret` ile doğrulanır. Kimlik ASLA tool parametresi olamaz; `X-User-Roles` bilerek downstream'e iletilmez (AI servisi admin yetkisi kazanamaz). Asıl yetki kararı downstream mikroservistedir; Python katmanı ikinci savunma hattıdır.
- **Fail-Fast Başlangıç (`startup_checks`):** `ENVIRONMENT != development` iken varsayılan veya 32 karakterden kısa secret ile servis ayağa kalkmaz (çıkış kodu 1).
- **Ayrık Audit Kaydı:** Denetim kayıtları ayrık `audit` logger'ı (`propagate=False`, stdout JSON) üzerinden tutulur. PII (kullanıcı mesajı, sipariş no, adres vb.) içermez; yalnızca kullanıcı UUID, `arg_names` ve `args_hash` yer alır. `ToolResult.reason` iç sınıflama içindir, modele/kullanıcıya yansıtılmaz. Arka arkaya yetkisiz erişim denemeleri (`enumeration_suspected`) alarm üretir.
- **Audit Saklama ve Değiştirilemezlik:** Audit akışı stdout'tan toplanır; uygulama logundan ayrı bir index/saklama süresi (örn. 1 yıl) ve değiştirilemezlik (WORM/immutability) altyapı (Loki/Elasticsearch) seviyesinde sağlanmalıdır; Python çalışma zamanı bunu garanti etmez.
- **Yeni Araç (Tool) Kontrol Listesi:**
  - [ ] Parametre şeması `extra="forbid"`; kimlik (`customer_id` vb.) parametresi yok.
  - [ ] Kaynağa erişimde sahiplik kontrolü yapılır; uyuşmazlıkta `ToolResult(..., reason="ownership_mismatch")`.
  - [ ] Hata metni 403 ve 404 için aynıdır ("bulunamadı"), varlık ifşa edilmez.
  - [ ] Araç `ToolRegistry`'ye kayıtlıdır (audit sarmalaması otomatik).
  - [ ] Yan etkili araç yalnızca `PendingAction` teklifi üretir; çalıştırma `ActionExecutor` + kullanıcı onayı ile yürütülür.

## 8. Gözlemlenebilirlik (Observability: Tracing, JSON Loglama, Metrikler ve Sağlık Denetimi)
- **Üç Kimlik Rolü (IDs):**
  - `Trace ID`: OpenTelemetry tarafından oluşturulur, gateway'den downstream servislere ve Kafka mesaj başlıklarına W3C `traceparent` ile taşınır (Tempo dağıtık izleme).
  - `Correlation ID`: API Gateway tarafından oluşturulur (`X-Correlation-Id`), `RequestContext` ve `correlation_id_var` (`ContextVar`) ile taşınır, JSON log satırlarına ve Kafka başlıklarına basılır (Loki iş akışı korelasyonu).
  - `Event ID`: Olayı üreten servis tarafından tekil UUIDv4 üretilir, Kafka event envelope `eventId` alanında taşınır (Idempotency tekilleştirme).
- **Observability Paket Haritası (`app/observability/`):**
  - `tracing.py`: OTLP HTTP trace dışa aktarımı, FastAPI ve HTTPX otomatik enstrümantasyonu, probe path filtreleme (`/health`, `/actuator/**`).
  - `context.py`: `correlation_id_var` ContextVar ve CRLF/uzunluk güvenlik süzgecine sahip saf ASGI `RequestContextMiddleware`.
  - `logging.py`: Root logger stdout yönlendirmesi, Java MDC uyumlu (`traceId`, `spanId`, `correlationId`) tek satır `JsonLogFormatter`, formatter seviyesinde `mask_pii` filtresi (mesaj ve stack trace).
  - `propagation.py`: Kafka mesajları için W3C `traceparent` ve `X-Correlation-Id` başlıklarını üreten `build_kafka_headers`.
  - `metrics.py`: `http_server_requests_seconds`, `ai_tool_call_duration_seconds`, `ai_llm_request_duration_seconds`, `ai_llm_tokens_total` Prometheus histogram ve sayaçları; route şablonunu çıkaran `HttpMetricsMiddleware`.
  - `health.py`: Liveness ve Readiness denetim mantığı (`check_readiness`).
- **Kardinalite ve Etiket (Label) Kuralları:**
  - Prometheus ve Loki'de `user_id`, `trace_id`, `correlation_id`, sipariş no veya ham dinamik URL path KESİNLİKLE label yapılamaz.
  - HTTP isteklerinde route daima şablona (`/agent/actions/{action_id}/confirm`) normalize edilir; 404 rotalar `UNMATCHED` olur.
  - Modelin uydurduğu araç adları `unknown` etiketine indirgenir.
  - `application` etiketi kodda tanımlanmaz; Prometheus scrape yapılandırması tarafından statik eklenir.
- **Kafka Üretici (Producer) Kontrol Listesi:**
  - Yeni bir Kafka producer yazıldığında mesaj gönderimi MUTLAKA `trace.SpanKind.PRODUCER` span'i içine alınmalı ve başlıklar `build_kafka_headers(event.get("correlationId"))` ile eklenmelidir.
- **Readiness ve Liveness Ayrımı:**
  - Liveness her zaman 200 döner (event loop donmadıysa canlıdır).
  - Readiness YALNIZCA açılış tamamlanması (`ready=True`), drain olmaması (`draining=False`) ve (varsa) Redis pingine bakar.
  - **Dış LLM Sağlayıcısı (Gemini, OpenAI), Qdrant veya downstream servisler KESİNLİKLE readiness'e eklenemez.** Dış kesintiler pod öldürülerek değil, uygulama içi fallback/circuit breaker ile yönetilir.
- **Async Bağlam Koruması:**
  - Kod içinde `run_in_executor` veya `ThreadPoolExecutor` kullanımı `copy_context` olmadan YASAKTIR (`asyncio.to_thread` ve `create_task` güvenle kullanılabilir).



