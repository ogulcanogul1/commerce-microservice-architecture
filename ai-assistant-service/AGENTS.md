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
