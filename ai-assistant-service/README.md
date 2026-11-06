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
# Ağsız / Docker'sız tüm testleri çalıştır (324 test)
uv run pytest -m "not integration"

# Yalnızca Generation testlerini çalıştır
uv run pytest tests/generation/ -v

# Yalnızca API testlerini çalıştır
uv run pytest tests/api/ -v

# Yalnızca vektör deposu testlerini çalıştır
uv run pytest tests/vectorstore/ -v
```
