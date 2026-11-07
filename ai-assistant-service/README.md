# AI Assistant Service (`ai-assistant-service`)

Commerce Platform Poliglot Yapay Zeka Alışveriş ve Destek Asistanı Servisi.

## Teknoloji Yığını
- **Python 3.12+**
- **FastAPI & Uvicorn**
- **Qdrant Vector Store** (Dense Cosine + Sparse BM25 + Sunucu Taraflı RRF Hibrit Füzyon)
- **Pydantic v2 & Pydantic Settings**
- **Astral `uv`** (Paket ve Ortam Yöneticisi)

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

---

## 2. Yerel Geliştirme ve Servisi Başlatma

```powershell
cd ai-assistant-service

# Bağımlılıkları senkronize et
uv sync

# Servisi başlat (Port: 8089)
uv run uvicorn app.main:app --reload --port 8089
```

- **Sağlık Kontrolü:** `http://localhost:8089/health`
- **Swagger UI Dokümantasyonu:** `http://localhost:8089/docs`

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

---

## 7. RAG Generation Değerlendirme ve Eşik Ölçümü (CLI)

```powershell
# 1. Answer Set veri setini doğrula
uv run python -m app.rag.evaluation.generation.dataset --validate

# 2. Dense kosinüs skor dağılımını ölç ve abstain eşiği önerisi al (Gate)
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
| `RAG_LLM_PROVIDER` | `""` | LLM sağlayıcısı (boşsa `DEFAULT_LLM_PROVIDER` kullanılır: openai, claude, gemini, local) |
| `RAG_LLM_MODEL` | `""` | Sağlayıcıya özel model kimliği (boşsa sağlayıcının varsayılanı) |
| `RAG_TEMPERATURE` | `0.0` | Üretim sıcaklığı (deterministik ve politikaya sadık cevaplar için 0.0) |
| `RAG_MAX_OUTPUT_TOKENS` | `400` | Üretilecek maksimum cevap uzunluğu (token) |
| `RAG_LLM_TIMEOUT_SEC` | `30.0` | LLM HTTP çağrısı zaman aşımı süresi (saniye) |
| `RAG_CONTEXT_TOKEN_BUDGET`| `1500` | Soruya eklenecek kaynak blokları için toplam token bütçesi |
| `RAG_TOP_K` | `5` | Getirilecek aday chunk sayısı |
| `RAG_MIN_DENSE_SCORE` | `None` | Abstain kapısı için minimum dense benzerlik eşiği (None = kapı kapalı) |
| `RAG_MAX_ATTEMPTS` | `2` | Doğrulama hatasında maksimum deneme sayısı (1 ilk deneme + 1 retry) |
| `RAG_ABSTAIN_MESSAGE` | `"Bu konuda dokümanlarımızda bilgi bulamadım..."` | Cevap bulunamadığında dönen kurumsal mesaj |

---

## 9. Testleri Çalıştırma

Tüm birim testleri Docker veya harici ağ gerektirmeden bellek içi (`:memory:`) modda koşturmak için:

```powershell
# Ağsız / Docker'sız tüm testleri çalıştır (457 test)
uv run pytest -m "not integration"

# Yalnızca Agent ve Güvenlik testlerini çalıştır
uv run pytest tests/agent/ -v

# Yalnızca API testlerini çalıştır
uv run pytest tests/api/ -v

# Yalnızca Generation testlerini çalıştır
uv run pytest tests/generation/ -v
```

---

## 10. Müşteri Destek Asistanı HTTP Uç Noktaları

Tüm asistan uç noktaları API Gateway üzerinden kimlik doğrulamalı istekleri kabul eder. İstemci `X-User-Id` (UUIDv4) ve `X-Gateway-Secret` başlıklarını sağlamakla yükümlüdür.

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

---

## 11. Agent Değerlendirme Çerçevesi (Agent Eval CLI)

Asistanın araç seçim doğruluğunu, onay süreçlerini ve sızıntı/güvenlik sınırlarını deterministik olarak değerlendirmek için:

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
| `GATEWAY_INTERNAL_SECRET` | `"dgl-internal-gateway-secret-token-2026"` | Ağ geçidi doğrudan erişim koruma anahtarı |
| `GATEWAY_SECURITY_ENABLED`| `true` | Ağ geçidi gizli anahtar doğrulamasının aktifliği |
| `ORDER_SERVICE_URL` | `"http://localhost:8082"` | Downstream Sipariş Servisi kök adresi |
| `SHIPPING_SERVICE_URL` | `"http://localhost:8085"` | Downstream Kargo Servisi kök adresi |
| `DOWNSTREAM_TIMEOUT_SEC` | `5.0` | Mikroservis HTTP çağrıları zaman aşımı süresi |
| `AGENT_LLM_PROVIDER` | `""` | Ajan LLM sağlayıcısı (boşsa `DEFAULT_LLM_PROVIDER`) |
| `AGENT_LLM_MODEL` | `""` | Ajan model kimliği |
| `AGENT_TEMPERATURE` | `0.0` | Deterministik ReAct adımları için model sıcaklığı |
| `AGENT_MAX_OUTPUT_TOKENS` | `500` | Ajanın adım başına üretebileceği maksimum token |
| `AGENT_LLM_TIMEOUT_SEC` | `30.0` | Ajan LLM çağrısı zaman aşımı süresi |
| `AGENT_TOOL_TIMEOUT_SEC` | `8.0` | Tekil araç çalıştırma zaman aşımı süresi |
| `AGENT_MAX_STEPS` | `4` | Maksimum ReAct döngü adım sayısı |
| `AGENT_PENDING_TTL_SEC` | `300` | Bekleyen onaylı işlem süresi (5 dakika) |
| `TICKET_PUBLISHER` | `"log"` | Destek bileti yayıncısı (`log` veya `kafka`) |
| `KAFKA_BOOTSTRAP_SERVERS`| `"localhost:9092"` | Kafka broker adresi |
| `SUPPORT_TICKET_TOPIC` | `"support.ticket.created"` | Destek biletleri Kafka konu başlığı |

---

## 13. Reranker Altyapısı (Opsiyonel İki Aşamalı Arama & A/B Ölçüm)

Platform, hibrit arama (Dense Cosine + Sparse BM25 + Sunucu Taraflı RRF) sonuçlarının üzerine opsiyonel bir ikinci aşama (cross-encoder reranking) katmanı içerir.
`RAG_RERANK_ENABLED=False` (varsayılan) iken arama doğrudan hibrit sonuçları döner, sistemde sıfır gecikme ve sıfır ağır kütüphane import yükü oluşturur.

### Yerel Model Bağımlılıkları Kurulumu
Yerel cross-encoder modeli (`BAAI/bge-reranker-v2-m3`) çalıştırmak için opsiyonel bağımlılık grubu:
```powershell
uv sync --extra local-embedding
```

### Retrieval A/B Karşılaştırması (`compare.py`)
Mevcut retrieval veri seti üzerinde temel hibrit arama ile reranker performansını (MRR, Hit@k, rank kaymaları) kıyaslar:
```powershell
# Fake reranker ile duman testi (ağsız)
uv run python -m app.rag.evaluation.rerank.compare --reranker fake

# Gerçek yerel model ile kıyaslama (candidates=20, top-k=3)
uv run python -m app.rag.evaluation.rerank.compare --reranker cross_encoder --rerank-model BAAI/bge-reranker-v2-m3 --candidates 20 --top-k 3
```

### Generation A/B Değerlendirmesi ve Rapor Fark Analizi (`reports_diff.py`)
Üretim aşamasında reranker etkisini (doğruluk, halüsinasyon, çekinme kararları) uçtan uca ölçmek için:
```powershell
# 1. Temel değerlendirme (Rerank kapalı)
uv run python -m app.rag.evaluation.generation.run --llm fake --output-file eval/rag/reports/baseline.json

# 2. Rerank devrede değerlendirme (Fail-closed eval)
uv run python -m app.rag.evaluation.generation.run --llm fake --rerank on --reranker fake --output-file eval/rag/reports/rerank_on.json

# 3. İki rapor arasındaki fark analizi (Metrik deltaları, flip tablosu, halüsinasyon uyarıları)
uv run python -m app.rag.evaluation.rerank.reports_diff eval/rag/reports/baseline.json eval/rag/reports/rerank_on.json

# 4. Dense ve Rerank skor dağılımlarını yan yana ölçme (Eşik önerisi yapmaz)
uv run python -m app.rag.evaluation.generation.gate --rerank
```

---

## 14. Reranker Yapılandırma Parametreleri

| Ortam Değişkeni | Varsayılan | Açıklama |
| :--- | :--- | :--- |
| `RAG_RERANK_ENABLED` | `false` | İki aşamalı reranker katmanını aktif/pasif eder (`true`/`false`) |
| `RAG_RERANK_PROVIDER` | `"cross_encoder"` | Reranker sağlayıcısı (`fake`, `cross_encoder`, `cohere`) |
| `RAG_RERANK_MODEL` | `"BAAI/bge-reranker-v2-m3"` | Reranker model kimliği (Cohere için varsayılan `rerank-v3.5`) |
| `RAG_RERANK_CANDIDATES` | `20` | Reranker'a gönderilecek birinci aşama (hibrit) aday sayısı |
| `RAG_RERANK_TIMEOUT_SEC` | `2.0` | Reranker çağrısı zaman aşımı süresi |
| `RAG_RERANK_FAIL_OPEN` | `true` | Üretimde hata durumunda hibrit ilk k adayı dönme (`true`). Eval için `false`. |
| `COHERE_API_KEY` | `""` | Cohere sağlayıcısı için API anahtarı (cross_encoder veya fake için gerekmez) |


