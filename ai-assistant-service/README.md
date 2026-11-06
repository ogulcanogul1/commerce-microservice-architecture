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

---

## 6. Testleri Çalıştırma

Tüm birim testleri Docker veya harici ağ gerektirmeden bellek içi (`:memory:`) modda koşturmak için:

```powershell
# Ağsız / Docker'sız tüm testleri çalıştır (231 test)
uv run pytest -m "not integration"

# Yalnızca API testlerini çalıştır
uv run pytest tests/api/ -v

# Yalnızca vektör deposu testlerini çalıştır
uv run pytest tests/vectorstore/ -v
```
