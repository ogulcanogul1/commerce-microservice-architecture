# AI Assistant Service (`ai-assistant-service`)

Commerce Platform'un poliglot (Python) yapay zeka alışveriş ve destek asistanı servisi.

İki ana yetenek sunar:

- **RAG (Retrieval-Augmented Generation):** Şirket politikası dokümanlarında (PDF) hibrit arama yapar ve yalnızca kaynağa dayanan, atıflı (citation) cevaplar üretir. Kaynakta bilgi yoksa uydurmak yerine çekinir (abstain).
- **Müşteri Destek Agent'ı:** Sipariş ve kargo sorgulayan, politika arayan, sipariş iptali ve destek bileti gibi hassas işlemleri **kullanıcı onayı olmadan yürütmeyen** (human-in-the-loop) bir ReAct agent'ı.

Servis Eureka'ya kendini kaydeder ve API Gateway (`lb://ai-assistant-service`) arkasında çalışır.

---

## İçindekiler

1. [Teknoloji Yığını ve Modül Haritası](#teknoloji-yığını)
2. [Altyapı ve Hazırlık](#1-altyapı-ve-hazırlık)
3. [Yerel Geliştirme ve Docker](#2-yerel-geliştirme-ve-servisi-başlatma)
4. [Doküman İndeksleme (CLI)](#3-doküman-i̇ndeksleme-ve-incremental-sync-cli)
5. [RAG Uç Noktaları](#5-rag-arama-http-uç-noktası-post-ragsearch)
6. [Agent Uç Noktaları](#10-müşteri-destek-asistanı-http-uç-noktaları)
7. [Dayanıklılık ve Hata Modeli](#13-dayanıklılık-limitler-ve-hata-modeli)
8. [Eureka Service Discovery](#14-eureka-service-discovery-ve-graceful-drain)
9. [Testler](#9-testleri-çalıştırma)

---

## Teknoloji Yığını

- **Python 3.12+**, **FastAPI & Uvicorn**
- **Qdrant Vector Store** (Dense Cosine + Sparse BM25 + sunucu taraflı RRF hibrit füzyon)
- **LLM Sağlayıcıları:** Gemini (varsayılan), OpenAI, Claude, yerel (OpenAI uyumlu) model
- **Reranker (opsiyonel):** Cross-Encoder (`BAAI/bge-reranker-v2-m3`) veya Cohere
- **Pydantic v2 & Pydantic Settings**, **httpx** (downstream ve Eureka REST çağrıları)
- **Eureka REST istemcisi** (harici kütüphane yok, `app/discovery/`)
- **Astral `uv`** (paket ve ortam yöneticisi)

### Modül Haritası (`app/`)

| Paket | Sorumluluk |
| :--- | :--- |
| `api/` | HTTP uç noktaları (`/rag/search`, `/rag/answer`, `/agent`, `/api/v1/chat`) |
| `agent/` | ReAct agent döngüsü, araçlar (tools), bekleyen aksiyon deposu, grounding, destek bileti yayıncısı |
| `rag/ingestion/` | PDF yükleme, temizleme, kalite triyajı ve sayfa birleştirme |
| `rag/chunking/` | Fixed-size, recursive ve structure-aware chunking stratejileri |
| `rag/embedding/` | Embedding sağlayıcıları, batching ve cache |
| `rag/vectorstore/` | Qdrant deposu, hibrit arama, sparse BM25, artımlı senkronizasyon |
| `rag/rerank/` | İki aşamalı arama için reranker protokolü ve sağlayıcıları |
| `rag/generation/` | Context oluşturma, prompt, citation doğrulama, abstain kararı |
| `rag/evaluation/`, `agent/evaluation/` | Offline değerlendirme CLI'ları ve raporlar |
| `llm/` | LLM sağlayıcı soyutlaması ve fabrikası |
| `clients/` | `order-service` ve `shipping-service` HTTP istemcileri |
| `discovery/` | Eureka kaydı, heartbeat, graceful drain |
| `core/` | Ayarlar, gateway güvenliği, RFC 7807 hata modeli, eşzamanlılık ve gövde boyutu limitleri, PII maskeleme |

---

## 1. Altyapı ve Hazırlık

Qdrant vektör veritabanını Docker ile başlatmak için:

```powershell
# Ana dizinde (commerce kök dizini)
docker compose up -d qdrant
```

- **Qdrant REST API:** `http://localhost:6333`
- **Qdrant Web Konsolu:** `http://localhost:6333/dashboard`
- **Qdrant gRPC:** `localhost:6334`

LLM ve embedding için ilgili API anahtarları `.env` dosyasında tanımlanır (`GEMINI_API_KEY`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`). Anahtar olmadan da servis ayağa kalkar; ilgili bileşenler başlatılamazsa log'a uyarı düşülür ve uç noktalar `503` döner.

---

## 2. Yerel Geliştirme ve Servisi Başlatma

```powershell
cd ai-assistant-service

# Bağımlılıkları senkronize et
uv sync

# Opsiyonel bağımlılıklar
uv sync --extra local-embedding   # yerel embedding / cross-encoder reranker
uv sync --extra kafka             # TICKET_PUBLISHER=kafka için aiokafka

# Servisi başlat (Port: 8089)
uv run uvicorn app.main:app --reload --port 8089
```

- **Sağlık Kontrolü:** `http://localhost:8089/health` (kimlik doğrulamasız; Eureka ve container healthcheck tarafından kullanılır)
- **Swagger UI Dokümantasyonu:** `http://localhost:8089/docs`
- **Gateway üzerinden OpenAPI:** `http://localhost:8080/v3/api-docs/ai-assistant-service`

### Docker ile Çalıştırma

Servisin `Dockerfile`'ı `python:3.12-slim` + `uv` tabanlıdır ve `docker-compose.apps.yml` içinde Eureka, Redis ve Kafka bağımlılıklarıyla tanımlıdır:

```powershell
# Ana dizinde
docker compose -f docker-compose.yml -f docker-compose.apps.yml up -d --build ai-assistant-service
```

> **Önemli — Tek worker:** Container içinde uvicorn **tek worker** ile çalışır (`--workers` verilmez). Birden fazla worker aynı instance'ı Eureka'ya birden çok kez kaydeder ve heartbeat'ler çakışır. Ölçekleme container replikalarıyla yapılır.
>
> `--timeout-graceful-shutdown 75` değeri, SIGTERM sonrası Eureka drain süresinin (§14) ve süren LLM turlarının tamamlanmasına izin verecek şekilde seçilmiştir.

> **Not:** Bekleyen aksiyonlar süreç belleğinde (`InMemoryPendingActionStore`) tutulur. Bu nedenle servis tek replika ile çalıştırılmalıdır: `chat` bir instance'ta aksiyon üretip `confirm` başka bir instance'a düşerse `404` alınır.

---

## 3. Doküman İndeksleme ve Incremental Sync (CLI)

Dokümanları yapısal parmak izi (`doc_hash`) ile artımlı olarak indekslemek için:

```powershell
# Kuru çalıştırma (dry-run) - Qdrant'a yazmadan ne yapılacağını gösterir
uv run python -m app.rag.vectorstore.sync --docs-dir tests/fixtures/contracts --dry-run

# Gerçek senkronizasyon (değişmeyen dokümanlar atlanır, maliyet 0)
uv run python -m app.rag.vectorstore.sync --docs-dir tests/fixtures/contracts

# Klasörden kaldırılan dokümanları koleksiyondan da temizlemek için (--prune)
uv run python -m app.rag.vectorstore.sync --docs-dir tests/fixtures/contracts --prune
```

---

## 4. Bellek İçi vs Qdrant Parite Değerlendirmesi (CLI)

In-Memory BM25/Dense ile Qdrant hibrit arama motorunu aynı altın soru kümesi üzerinde kıyaslamak için:

```powershell
# Fake embedder ile offline test
uv run python -m app.rag.evaluation.qdrant.parity --embedder fake

# Varsayılan üretim embedding modeli ile test (API anahtarı gerekir)
uv run python -m app.rag.evaluation.qdrant.parity --embedder default
```

Otomatik rapor `eval/qdrant/reports/` dizinine Markdown ve JSON olarak üretilir.

---

## 5. RAG Arama HTTP Uç Noktası (`POST /rag/search`)

> Tüm `/rag/*` ve `/agent/*` uç noktaları `X-Gateway-Secret` başlığı ister (bkz. §10). Örneklerde kısalık için gösterilmemiştir.

```http
POST /rag/search
Content-Type: application/json

{
  "query": "İade süresi kaç gündür?",
  "k": 5,
  "mode": "hybrid",
  "source_file": "iade_politikasi.pdf"
}
```

**Örnek Başarılı Yanıt (200 OK):**
```json
{
  "hits": [
    {
      "chunk_id": "chunk-iade-1",
      "score": 0.03278,
      "text": "İade süresi ürün tesliminden itibaren 14 gündür. Kargo ücretsizdir.",
      "source_file": "iade_politikasi.pdf",
      "page_start": 2,
      "page_end": 2,
      "heading_path": ["İade Politikası", "Süre"]
    }
  ]
}
```

---

## 6. RAG Cevap Üretimi HTTP Uç Noktası (`POST /rag/answer`)

```http
POST /rag/answer
Content-Type: application/json
X-Correlation-Id: test-correlation-id

{
  "question": "Müşteriler siparişlerini kaç gün içinde iade edebilir?",
  "k": 3,
  "source_file": "iade_politikasi.pdf"
}
```

**Örnek Başarılı Yanıt (200 OK):**
```json
{
  "status": "answered",
  "answer": "Tüketiciler, satın aldıkları ürünleri teslim tarihinden itibaren 14 gün içinde herhangi bir gerekçe göstermeksizin iade edebilirler [1].",
  "abstain_reason": null,
  "citations": [
    {
      "number": 1,
      "chunk_id": "chunk-iade-politikasi-p1-c0",
      "source_file": "iade_politikasi.pdf",
      "page_start": 1,
      "page_end": 1,
      "heading_path": ["1. Genel İade Koşulları"]
    }
  ]
}
```

**Örnek Abstain Yanıtı (200 OK):**
```json
{
  "status": "abstained",
  "answer": "Bu konuda dokümanlarımızda bilgi bulamadım. Sizi bir müşteri temsilcisine yönlendirebilirim.",
  "abstain_reason": "model_abstained",
  "citations": []
}
```

Bu uç nokta eşzamanlılık limiti ve `RAG_TURN_TIMEOUT_SEC` tur bütçesiyle korunur (bkz. §13).

---

## 7. RAG Generation Değerlendirme ve Threshold Ölçümü (CLI)

```powershell
# 1. Answer Set veri setini doğrula (54 soru: 42 cevaplanabilir, 12 cevaplanamaz)
uv run python -m app.rag.evaluation.generation.dataset --validate

# 2. Dense kosinüs skor dağılımını ölç ve abstain threshold önerisi al (Gate)
uv run python -m app.rag.evaluation.generation.gate --embedder fake

# 3. Uçtan uca generation kalite değerlendirmesi çalıştır (Smoke Test - Fake LLM)
uv run python -m app.rag.evaluation.generation.run --llm fake --embedder fake

# 4. Gerçek LLM ile değerlendirme (API anahtarları ile)
uv run python -m app.rag.evaluation.generation.run --llm default --embedder default
```

Otomatik raporlar `eval/generation/reports/` dizinine Markdown (`.md`) ve JSON formatında üretilir.

---

## 8. RAG Yapılandırma Parametreleri

| Ortam Değişkeni | Varsayılan | Açıklama |
| :--- | :--- | :--- |
| `DEFAULT_LLM_PROVIDER` | `"gemini"` | Ortak varsayılan LLM sağlayıcısı (`openai`, `claude`, `gemini`, `local`) |
| `EMBEDDING_PROVIDER` | `"openai"` | Embedding sağlayıcısı |
| `EMBEDDING_MODEL` | `"text-embedding-3-small"` | Embedding model kimliği |
| `QDRANT_URL` | `"http://localhost:6333"` | Qdrant adresi |
| `QDRANT_COLLECTION_PREFIX` | `"commerce_docs"` | Koleksiyon adı ön eki |
| `RAG_LLM_PROVIDER` | `""` | RAG LLM sağlayıcısı (boşsa `DEFAULT_LLM_PROVIDER`) |
| `RAG_LLM_MODEL` | `""` | Sağlayıcıya özel model kimliği (boşsa sağlayıcının varsayılanı) |
| `RAG_RETRIEVAL_MODE` | `"hybrid"` | Retrieval modu (`dense`, `sparse`, `hybrid`) |
| `RAG_TEMPERATURE` | `0.0` | Üretim sıcaklığı (deterministik ve politikaya sadık cevaplar için 0.0) |
| `RAG_MAX_OUTPUT_TOKENS` | `400` | Üretilecek maksimum cevap uzunluğu (token) |
| `RAG_LLM_TIMEOUT_SEC` | `30.0` | Tekil LLM HTTP çağrısı zaman aşımı (saniye) |
| `RAG_CONTEXT_TOKEN_BUDGET`| `1500` | Soruya eklenecek kaynak blokları için toplam token bütçesi |
| `RAG_TOP_K` | `5` | Getirilecek aday chunk sayısı |
| `RAG_MIN_DENSE_SCORE` | `None` | Abstain kapısı için minimum dense benzerlik threshold'u (None = kapı kapalı) |
| `RAG_MAX_ATTEMPTS` | `2` | Doğrulama hatasında maksimum deneme sayısı (1 ilk deneme + 1 retry) |
| `RAG_ABSTAIN_MESSAGE` | `"Bu konuda dokümanlarımızda bilgi bulamadım..."` | Cevap bulunamadığında dönen kurumsal mesaj |

---

## 9. Testleri Çalıştırma

Tüm birim testleri Docker, harici ağ, gerçek Eureka/Redis ve model indirme gerektirmeden çalışır:

```powershell
# Ağsız / Docker'sız tüm testleri çalıştır (570 test, ~30 sn)
uv run pytest -m "not integration"

# Gerçek API / ağ gerektiren entegrasyon testleri
uv run pytest -m integration

# Yalnızca Agent ve Güvenlik testlerini çalıştır
uv run pytest tests/agent/ -v

# Yalnızca API testlerini çalıştır
uv run pytest tests/api/ -v

# Yalnızca Generation testlerini çalıştır
uv run pytest tests/generation/ -v
```

---

## 10. Müşteri Destek Asistanı HTTP Uç Noktaları

Tüm asistan uç noktaları API Gateway üzerinden kimlik doğrulamalı istekleri kabul eder. Gateway, JWT'yi doğruladıktan sonra `X-User-Id` (UUIDv4) ve `X-Gateway-Secret` başlıklarını ekler. Servise doğrudan port üzerinden gelen ve geçerli secret taşımayan istekler reddedilir.

Agent router'ı iki ön ek altında yayınlanır; ikisi de aynı uç noktalara gider:

| Yol | Açıklama |
| :--- | :--- |
| `POST /agent/chat` veya `POST /agent` | Sohbet turu |
| `POST /api/v1/chat` | Gateway'in istemciye açtığı sohbet yolu (aynı handler) |
| `POST /agent/actions/{action_id}/confirm` | Bekleyen aksiyonu onayla |
| `POST /agent/actions/{action_id}/reject` | Bekleyen aksiyonu reddet |

Gateway rotası (`api-gateway/src/main/resources/application.yaml`): `/api/v1/chat/**`, `/agent/**`, `/rag/**` → `lb://ai-assistant-service`, `aiAssistantCircuitBreaker` ile.

### A. Asistanla Konuşma (`POST /agent/chat`)
```bash
curl -X POST "http://localhost:8089/agent/chat" \
  -H "Content-Type: application/json" \
  -H "X-User-Id: aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa" \
  -H "X-Gateway-Secret: dgl-internal-gateway-secret-token-2026" \
  -d '{
    "message": "ORD-1001 nolu siparişimi iptal etmek istiyorum."
  }'
```

`message` alanı en fazla 1000 karakterdir.

**Örnek Yanıt (Onay Bekleyen Aksiyon - 200 OK):**
```json
{
  "kind": "pending_action",
  "reply": "ORD-1001 numaralı siparişi iptal etmek istediğinizi onaylıyor musunuz? Sebep: Müşteri isteği",
  "citations": [],
  "pending_action": {
    "action_id": "act_xK91aBcDeFgHiJkLmNoPqRsTuV",
    "action_type": "cancel_order",
    "summary": "ORD-1001 numaralı siparişi iptal etmek istediğinizi onaylıyor musunuz? Sebep: Müşteri isteği",
    "expires_at": "2026-11-07T14:40:00Z"
  }
}
```

### B. Bekleyen İşlemi Onaylama (`POST /agent/actions/{action_id}/confirm`)
```bash
curl -X POST "http://localhost:8089/agent/actions/act_xK91aBcDeFgHiJkLmNoPqRsTuV/confirm" \
  -H "X-User-Id: aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa" \
  -H "X-Gateway-Secret: dgl-internal-gateway-secret-token-2026"
```

**Örnek Yanıt (200 OK):**
```json
{
  "status": "executed",
  "message": "ORD-1001 numaralı sipariş başarıyla iptal edildi."
}
```

### C. Bekleyen İşlemi Reddetme (`POST /agent/actions/{action_id}/reject`)
```bash
curl -X POST "http://localhost:8089/agent/actions/act_xK91aBcDeFgHiJkLmNoPqRsTuV/reject" \
  -H "X-User-Id: aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa" \
  -H "X-Gateway-Secret: dgl-internal-gateway-secret-token-2026"
```

**Örnek Yanıt (200 OK):**
```json
{
  "status": "rejected",
  "message": "İşlem iptal edildi."
}
```

### Agent Araçları (Tools)

| Araç | Açıklama |
| :--- | :--- |
| `SearchPolicyTool` | Politika dokümanlarında RAG araması (yalnızca RAG servisi ayaktaysa kaydedilir) |
| `GetOrderTool` / `ListMyOrdersTool` | Kullanıcının kendi siparişlerini sorgular |
| `GetShipmentTool` | Siparişe bağlı kargo durumunu getirir |
| `RequestOrderCancellationTool` | Sipariş iptali için **onay bekleyen aksiyon** üretir, doğrudan iptal etmez |
| `RequestSupportTicketTool` | Destek bileti için **onay bekleyen aksiyon** üretir |

---

## 11. Agent Değerlendirme Çerçevesi (Agent Eval CLI)

Asistanın araç seçim accuracy'sini, onay süreçlerini ve sızıntı/güvenlik sınırlarını deterministik olarak değerlendirmek için:

```powershell
# 1. Değerlendirme veri setini doğrula (39 vaka)
uv run python -m app.agent.evaluation.dataset --validate

# 2. Uçtan uca smoke değerlendirme çalıştır (Fake LLM, ağsız)
uv run python -m app.agent.evaluation.run --llm fake

# 3. Gerçek model ile değerlendirme çalıştır (API anahtarı gerekir)
uv run python -m app.agent.evaluation.run --llm default
```

Otomatik raporlar `eval/agent/reports/` dizinine Markdown (`.md`) ve JSON formatında üretilir.

---

## 12. Agent Yapılandırma Parametreleri

| Ortam Değişkeni | Varsayılan | Açıklama |
| :--- | :--- | :--- |
| `GATEWAY_INTERNAL_SECRET` | `"dgl-internal-gateway-secret-token-2026"` | Gateway doğrudan erişim koruma anahtarı |
| `GATEWAY_SECURITY_ENABLED`| `true` | Gateway secret doğrulamasının aktifliği |
| `ORDER_SERVICE_URL` | `"http://localhost:8082"` | Downstream Sipariş Servisi kök adresi |
| `SHIPPING_SERVICE_URL` | `"http://localhost:8085"` | Downstream Kargo Servisi kök adresi |
| `DOWNSTREAM_TIMEOUT_SEC` | `5.0` | Mikroservis HTTP çağrıları zaman aşımı süresi |
| `AGENT_LLM_PROVIDER` | `""` | Agent LLM sağlayıcısı (boşsa `DEFAULT_LLM_PROVIDER`) |
| `AGENT_LLM_MODEL` | `""` | Agent model kimliği |
| `AGENT_TEMPERATURE` | `0.0` | Deterministik ReAct adımları için model sıcaklığı |
| `AGENT_MAX_OUTPUT_TOKENS` | `500` | Agent'ın adım başına üretebileceği maksimum token |
| `AGENT_LLM_TIMEOUT_SEC` | `30.0` | Tekil agent LLM çağrısı zaman aşımı |
| `AGENT_TOOL_TIMEOUT_SEC` | `8.0` | Tekil araç çalıştırma zaman aşımı |
| `AGENT_POLICY_TOOL_TIMEOUT_SEC` | `30.0` | `SearchPolicyTool` için ayrı zaman aşımı (içinde RAG + LLM çağrısı var) |
| `AGENT_MAX_STEPS` | `4` | Maksimum ReAct döngü adım sayısı |
| `AGENT_MAX_TOOL_RESULT_CHARS` | `2000` | Modele geri verilen araç sonucunun maksimum uzunluğu |
| `AGENT_PENDING_TTL_SEC` | `300` | Bekleyen onaylı işlem süresi (5 dakika) |
| `AGENT_FALLBACK_MESSAGE` | `"Şu an bu isteğinizi güvenle tamamlayamadım..."` | Agent güvenli cevap üretemediğinde dönen mesaj |
| `TICKET_PUBLISHER` | `"log"` | Destek bileti yayıncısı (`log` veya `kafka`) |
| `KAFKA_BOOTSTRAP_SERVERS`| `"localhost:9092"` | Kafka broker adresi |
| `SUPPORT_TICKET_TOPIC` | `"support.ticket.created"` | Destek biletleri Kafka topic'i |

---

## 13. Dayanıklılık, Limitler ve Hata Modeli

LLM çağrıları uzun (10–45 sn) ve maliyetli olduğundan servis istekleri kuyrukta bekletmez; kapasite dolduğunda hemen reddeder (fail-fast).

| Katman | Nerede | Davranış |
| :--- | :--- | :--- |
| **Gövde boyutu limiti** | `BodySizeLimitMiddleware` (`app/core/limits.py`) | `POST/PUT/PATCH` isteklerinde `Content-Length > AI_MAX_BODY_BYTES` ise gövde okunmadan `413` döner |
| **Eşzamanlılık limiti** | `ConcurrencyLimiter` (`app/core/limits.py`) | Instance başına aktif LLM turu `AI_MAX_CONCURRENT_REQUESTS`'e ulaşınca kuyruğa almadan `503` + `Retry-After: 5` döner |
| **Tur bütçesi (turn timeout)** | `app/api/agent.py`, `app/api/answer.py` | Tüm agent turu (≤4 LLM adımı + araçlar) `AGENT_TURN_TIMEOUT_SEC`, RAG turu (retrieval + ≤2 LLM denemesi) `RAG_TURN_TIMEOUT_SEC` ile sınırlanır; aşımda `503` |

Tur timeout'ları tekil çağrı timeout'larının (`*_LLM_TIMEOUT_SEC`, `AGENT_TOOL_TIMEOUT_SEC`) **üstünde** bir sınırdır: tekil çağrılar tek tek süreye uysa da toplamları bu bütçeyi aşamaz. Gateway tarafındaki timeout bu değerlerden büyük olmalıdır.

### RFC 7807 Hata Cevapları

Tüm hatalar `application/problem+json` formatında döner (`app/core/errors.py`). Hatalar `RetryableException` (geçici; `retryable: true`, `Retry-After`) ve `NonRetryableException` (kalıcı; `retryable: false`) olarak sınıflandırılır. İstemci serbest metin olan `detail` alanını değil, makine-okunabilir `type` URI'sini kontrol etmelidir.

**Örnek: Kapasite dolu (503):**
```json
{
  "type": "https://api.commerce.com/errors/ai-overloaded",
  "title": "Service Overloaded",
  "status": 503,
  "detail": "Asistan servisi şu anda maksimum eşzamanlı kapasiteye ulaştı. Lütfen birkaç saniye sonra tekrar deneyin.",
  "instance": "/api/v1/chat",
  "retryable": true,
  "retry_after_seconds": 5
}
```

**Örnek: Gövde çok büyük (413):**
```json
{
  "type": "about:blank",
  "title": "Payload Too Large",
  "status": 413,
  "detail": "İstek gövdesi izin verilen maksimum boyuttan büyük (120000 > 65536 bayt).",
  "instance": "/api/v1/chat",
  "retryable": false
}
```

| `type` | Durum | Anlamı |
| :--- | :--- | :--- |
| `about:blank` | çeşitli | Standart HTTP hataları (404, 413, 422, 503 vb.); 422'de `errors` listesi döner |
| `.../errors/ai-overloaded` | `503` | Eşzamanlılık kapasitesi dolu |
| `.../errors/token-budget-exceeded` | `429` | Kullanıcı veya sağlayıcı token bütçesi kotası aşıldı (`Retry-After` başlığı içerir) |
| `.../errors/budget-unavailable` | `503` | Bütçe deposu kapalı modda (`fail_mode=closed`) erişilemez durumda |

### Token Bütçesi ve Hız Sınırı Parametreleri

Gateway istek sayısını sınırlarken, `TokenBudgetService` kullanıcı ve sağlayıcı token harcamalarını önceden rezerve edip sonradan uzlaştırarak (`reserve & reconcile`) maliyet kontrolü sağlar. Redis üzerinde atomik Lua betikleri ile çalışır.

| Ortam Değişkeni | Varsayılan | Açıklama |
| :--- | :--- | :--- |
| `AI_MAX_CONCURRENT_REQUESTS` | `20` | Instance başına eşzamanlı LLM turu limiti |
| `AI_MAX_BODY_BYTES` | `65536` | Maksimum istek gövdesi (64 KB, en az 1024) |
| `AGENT_TURN_TIMEOUT_SEC` | `60.0` | Agent sohbet turunun toplam süre bütçesi |
| `RAG_TURN_TIMEOUT_SEC` | `45.0` | RAG cevaplama turunun toplam süre bütçesi |
| `TOKEN_BUDGET_ENABLED` | `false` | Token bütçesi kontrolünü aç/kapa |
| `TOKEN_BUDGET_DAILY_LIMIT` | `200000` | Kullanıcı başına günlük token limiti |
| `TOKEN_BUDGET_PER_MINUTE_LIMIT` | `20000` | Kullanıcı başına dakikalık token limiti |
| `TOKEN_BUDGET_PROVIDER_TPM_LIMIT` | `0` | Ortak sağlayıcı TPM limiti (0 = limitsiz) |
| `TOKEN_BUDGET_FAIL_MODE` | `"local"` | Redis arızasında davranış (`local` = in-memory fallback, `closed` = 503) |
| `REDIS_ENABLED` | `false` | Redis bağlantısını aç/kapa |
| `REDIS_HOST` | `"localhost"` | Redis sunucu adresi |
| `REDIS_PORT` | `6379` | Redis portu |
| `REDIS_PASSWORD` | `""` | Redis şifresi |

---

## 14. Eureka Service Discovery ve Graceful Drain

Servis, Spring Cloud Eureka'ya REST API üzerinden kendini `AI-ASSISTANT-SERVICE` adıyla kaydeder (`app/discovery/`). Gateway servisi `lb://ai-assistant-service` ile bulur. Yerel geliştirmede varsayılan olarak **kapalıdır** (`EUREKA_ENABLED=false`); Docker Compose'da açıktır.

- **`EurekaClient`**: register, heartbeat, deregister ve status değiştirme REST çağrıları.
- **`EurekaRegistrar`**: başlangıçta kayıt olur, `EUREKA_RENEWAL_SEC` aralığıyla heartbeat atar. Eureka erişilemezse uygulama çalışmaya devam eder (yalnızca uyarı log'u).
- **Graceful drain** (`install_sigterm_drain`): SIGTERM geldiğinde instance önce Eureka'dan çıkarılır, ardından `EUREKA_DRAIN_SEC` kadar beklenir. Bu sürede gateway'in önbelleğindeki eski kayıt düşer ve kapanan instance'a yeni istek gönderilmez. Süren istekler bu arada tamamlanır.
- **Host çözümleme** (`resolve_instance_host`): `SERVICE_HOST` verilmişse o kullanılır; aksi halde makinenin hostname/IP'si çözülür. Instance ID formatı: `{host}:ai-assistant-service:{port}`.
- Health URL olarak `/health` kaydedilir.

### Kesinti Penceresi Hesabı (Downtime Window)
- **Graceful Durdurma (SIGTERM):** `docker stop` -> Eureka'dan deregister -> 20 sn drain süresi. Gateway ve Eureka önbellekleri (Eureka Server read-cache: 5s, Gateway fetch: 5s, LoadBalancer TTL: 5s = toplam ~15s) bu 20s içinde güncellenir. Gateway artık eski instance'a istek göndermez; uçuştaki istekler kesintisiz tamamlanır (sıfır kesinti).
- **Ani Durdurma (SIGKILL / Çökme):** Heartbeat kesilir -> Lease expiration (30s) + Eviction timer (5s) + Gateway fetch (5s) + LoadBalancer cache (5s) = ~45s kesinti penceresi. Bu sürede Gateway Circuit Breaker fallback'leri devreye girer.

### Docker Compose ile Çoklu Replika Ölçekleme
Container başına kesinlikle tek bir Uvicorn worker'ı (`--workers 1`) çalışır. İki replika ile çalıştırmak için:
```powershell
docker compose -f docker-compose.yml -f docker-compose.apps.yml up -d --scale ai-assistant-service=2
```

| Ortam Değişkeni | Varsayılan | Açıklama |
| :--- | :--- | :--- |
| `EUREKA_ENABLED` | `false` | Eureka kaydını aç/kapa |
| `EUREKA_SERVER_URL` | `"http://localhost:8761/eureka/"` | Eureka sunucu adresi |
| `EUREKA_PREFER_IP` | `true` | Kayıtta hostname yerine IP tercih et |
| `SERVICE_HOST` | `""` | Kayıtta kullanılacak host (Compose'da container adı) |
| `PORT` | `8089` | Kayıtta ilan edilen port |
| `EUREKA_RENEWAL_SEC` | `10` | Heartbeat sıklığı (sn) |
| `EUREKA_LEASE_SEC` | `30` | Heartbeat kesilirse kaydın silinme süresi (sn) |
| `EUREKA_DRAIN_SEC` | `20` | SIGTERM sonrası deregister ile kapanış arasındaki bekleme (sn) |
| `EUREKA_REQUEST_TIMEOUT_SEC` | `3.0` | Eureka REST çağrısı timeout'u (sn) |

Kayıtları kontrol etmek için:
```powershell
curl http://localhost:8761/eureka/apps/AI-ASSISTANT-SERVICE -H "Accept: application/json"
```

---

## 15. Reranker Altyapısı (Opsiyonel İki Aşamalı Arama & A/B Ölçüm)

Platform, hibrit arama (Dense Cosine + Sparse BM25 + sunucu taraflı RRF) sonuçlarının üzerine opsiyonel bir ikinci aşama (cross-encoder reranking) katmanı içerir.
`RAG_RERANK_ENABLED=false` (varsayılan) iken arama doğrudan hibrit sonuçları döner; ek gecikme ve ağır kütüphane import yükü oluşmaz. Açık olduğunda Cross-Encoder modeli başlangıçta ısıtılır (warmup), böylece ilk istek gecikmesi yaşanmaz.

### Yerel Model Bağımlılıkları Kurulumu
Yerel cross-encoder modeli (`BAAI/bge-reranker-v2-m3`) çalıştırmak için opsiyonel bağımlılık grubu:
```powershell
uv sync --extra local-embedding
```

### Retrieval A/B Karşılaştırması (`compare.py`)
Mevcut retrieval veri seti üzerinde temel hibrit arama ile reranker performansını (MRR, Hit@k, rank kaymaları, kategori kırılımı) kıyaslar:
```powershell
# Fake reranker ile duman testi (ağsız)
uv run python -m app.rag.evaluation.rerank.compare --reranker fake

# Gerçek yerel model ile kıyaslama (candidates=20, top-k=3)
uv run python -m app.rag.evaluation.rerank.compare --reranker cross_encoder --rerank-model BAAI/bge-reranker-v2-m3 --candidates 20 --top-k 3
```

### Generation A/B Değerlendirmesi ve Rapor Fark Analizi (`reports_diff.py`)
Üretim aşamasında reranker etkisini (accuracy, halüsinasyon, abstain kararları) uçtan uca ölçmek için:
```powershell
# 1. Temel değerlendirme (Rerank kapalı)
uv run python -m app.rag.evaluation.generation.run --llm fake --output-file eval/rag/reports/baseline.json

# 2. Rerank devrede değerlendirme (Fail-closed eval)
uv run python -m app.rag.evaluation.generation.run --llm fake --rerank on --reranker fake --output-file eval/rag/reports/rerank_on.json

# 3. İki rapor arasındaki fark analizi (Metrik deltaları, flip tablosu, halüsinasyon uyarıları)
uv run python -m app.rag.evaluation.rerank.reports_diff eval/rag/reports/baseline.json eval/rag/reports/rerank_on.json

# 4. Dense ve Rerank skor dağılımlarını yan yana ölçme (Threshold önerisi yapmaz)
uv run python -m app.rag.evaluation.generation.gate --rerank
```

### Reranker Yapılandırma Parametreleri

| Ortam Değişkeni | Varsayılan | Açıklama |
| :--- | :--- | :--- |
| `RAG_RERANK_ENABLED` | `false` | İki aşamalı reranker katmanını aktif/pasif eder |
| `RAG_RERANK_PROVIDER` | `"cross_encoder"` | Reranker sağlayıcısı (`fake`, `cross_encoder`, `cohere`) |
| `RAG_RERANK_MODEL` | `""` | Boşsa sağlayıcının varsayılanı (`BAAI/bge-reranker-v2-m3` / Cohere için `rerank-v3.5`) |
| `RAG_RERANK_CANDIDATES` | `20` | Reranker'a gönderilecek birinci aşama (hibrit) aday sayısı (1..50) |
| `RAG_RERANK_TIMEOUT_SEC` | `10.0` | Reranker çağrısı zaman aşımı |
| `RAG_RERANK_FAIL_OPEN` | `true` | Üretimde hata durumunda hibrit ilk k adayı dön. Eval için `false` (fail-closed). |
| `COHERE_API_KEY` | `""` | Cohere sağlayıcısı için API anahtarı (cross_encoder veya fake için gerekmez) |

