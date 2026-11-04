# Embedding Karar Günlüğü

Bu belge, embedding modeli seçimi, boyut optimizasyonu ve retriever mimarisine dair verilen kararları ve gerekçelerini kayıt altına alır.

## Aday Modeller Karşılaştırma Tablosu

| Sağlayıcı / Model | Boyut (dim) | Max Token | Fiyat ($ / 1M token) | Türkçe Performansı | Sorgu / Doküman Öneki Kuralı |
|---|---|---|---|---|---|
| **OpenAI `text-embedding-3-small`** | 1536 (512 kısaltılabilir) | 8,191 | $0.02 | Güçlü | Önek yok (Query ve Doc aynı çağrı) |
| **OpenAI `text-embedding-3-large`** | 3072 (1536/256) | 8,191 | $0.13 | Çok Güçlü | Önek yok |
| **Google Gemini `text-embedding-004`** | 768 | 2,048 | $0.00 (Free tier) / $0.025 | İyi / Çok Dilli | `task_type`: `RETRIEVAL_QUERY` / `RETRIEVAL_DOCUMENT` |
| **Local `intfloat/multilingual-e5-small`** | 384 | 512 | $0.00 (Self-hosted) | Orta / İyi | Sorgu: `query: `, Doküman: `passage: ` (Zorunlu!) |
| **Local `BAAI/bge-m3`** | 1024 | 8,192 | $0.00 (Self-hosted) | Çok Güçlü (100+ dil) | Önek gerekmez |

---

## Adım Bazlı Kararlar

- **Adım 0 (Hazırlık):** Aday modeller belirlendi. Girdi metni olarak `Chunk.embedding_text` standardı ve çıktı olarak L2-normalized float32 vektörler kabul edildi.
- **Adım 1 (Modeller ve Interface):** `EmbedKind` (QUERY/DOCUMENT), immutable `EmbeddingConfig`, açık kalıtım ve fail-fast sözleşme garantisi sunan `Embedder(ABC)` interface'i ve sıfır vektör güvenliğine sahip `l2_normalize` fonksiyonu tanımlandı. (Kod okunabilirliğini ve IDE desteğini artırmak için Protocol yerine `abc.ABC` interface yapısına geçildi).
- **Adım 2 (FakeEmbedder):** Ağ bağımlılığı olmayan, feature hashing (MD5 bag-of-words) ile deterministik ve anlamsal benzerliği koruyan, çağrı/metin sayaçlarına sahip `FakeEmbedder` eklendi.
- **Adım 3 (Disk Cache):** SQLite tabanlı `DiskEmbeddingCache` ve eksik parçaları topluca sorgulayan `CachedEmbedder` wrapper'ı yazıldı. Cache anahtarında `(model_id, dimensions, kind, text)` karması kullanılarak gereksiz API harcamaları önlendi.
- **Adım 4 (Batching ve Retry):** `batched` dilimleme, boş string/whitespace reddi (`validate_non_empty_texts`) ve üstel geri çekilme + rastgele jitter içeren `with_retry` eklendi. AGENTS.md kuralı 8.7 doğrultusunda 4xx hatalarında fail-fast, 429 ve 5xx hatalarında retry stratejisi uygulandı.
- **Adım 5 (Provider'lar ve Factory):** `OpenAIEmbedder`, `GeminiEmbedder` (RETRIEVAL_QUERY/DOCUMENT task_type ile), `LocalEmbedder` (E5 'query:/passage:' ve BGE-M3 desteği ile) ve `get_embedder` fabrika fonksiyonu eklendi. Tüm çağrılar batching, retry ve l2_normalize ile sarmalandı.
- **Adım 6 (Dense ve Hybrid Retriever):** Bellek içi dot-product ile `DenseRetriever` ve Weighted Reciprocal Rank Fusion (`dense_weight` ve tamamlayıcı `bm25_weight = 1.0 - dense_weight`) ile Dense + BM25 birleştiren `HybridRetriever` yazıldı. Ortak bütçe mantığı `select_chunks_by_budget` yardımcısına çıkarılarak kod tekrarı önlendi.
- **Adım 7 (Token Limiti ve Chunking Uyumu):** `validate_chunks_fit` ve `compute_token_divergence_ratio` yardımcıları eklendi. `DefaultChunker` varsayılan ayarlarıyla (`max_tokens=300`) üretilen golden set korpusundaki tüm chunk'ların, en dar limitli adayımız olan `multilingual-e5-small` (512 token) dahil hiçbir model sınırını aşmadığı (`all_fit=True`) testlerle doğrulandı.
- **Adım 8 (Model Karşılaştırma Runner'ı):** CLI üzerinden çalışan `compare.py` tamamlandı. BM25 baseline'ı ile Dense ve Hybrid retriever'ları aynı chunk'lar ve 42 soruluk Golden Set üzerinde yarıştırıldı. Korpus doygunluk uyarısı (saturation detection), operasyonel ölçümler (gecikme, maliyet, depolama) ve otomatik Markdown + JSON raporlama başarıyla doğrulandı.
- **Adım 9 (Nihai Karar, Geçici Durum ve Devir):**
  1. **Seçilen Model ve Boyut (Geçici / Provisional):** `openai/text-embedding-3-small` (1536 dim, Qdrant maliyet optimizasyonu için Matryoshka 512 dim'e kısaltılabilir).
     - *Önemli Not:* Yerel geliştirme ortamında harici bulut API anahtarları (`OPENAI_API_KEY`, `GEMINI_API_KEY`) tanımlanmadığından, ilk benchmark koşusu yalnızca `fake/deterministic-bow` modeli ile tamamlanabilmiştir. Bu nedenle OpenAI seçimi deneysel bir zafer değil, teorik kriterlere (8,191 token geniş context penceresi, $0.02 / 1M token ultra düşük maliyet, güçlü Türkçe semantik başarımı ve önek kuralı gerektirmemesi) dayalı **geçici bir başlangıç adayıdır (provisional candidate)**.
  2. **Varsayılan Retriever Mimarisi:** `HybridRetriever` (Weighted Reciprocal Rank Fusion, `dense_weight=0.5` ve `bm25_weight=0.5`).
     - Pilot koşuda dahi bag-of-words tabanlı deterministik fake vektörlerle yapılan hibritleştirme (Dense %66.7 Hit@1, BM25 %81.0 Hit@1, Hibrit %88.1 Hit@1, MRR 0.889 -> 0.929) anahtar kelime araması ile vektör aramasının birbirini tamamladığını göstermiştir.
  3. **Yapısal Korpus Doygunluğu ve Yeniden Doğrulama:**
     - Mevcut test korpusu 3 PDF ve toplam 8 chunk'tan oluşmaktadır. 8 chunk'lık bir korpusta `top_k=5` çağrıldığında chunk'ların %62'si doğrudan seçildiği için Hit@3 ve Hit@5 oranlarının %95-%100'e ulaşması istatistiksel bir başarı değil, **yapısal bir doygunluk (structural saturation)** sonucudur.
     - Canlı e-ticaret ürün kataloğu ve zengin politika dokümanları yüklendiğinde ve API anahtarları tanımlandığında Adım 8 şu komutla yeniden koşturulmalıdır:
       ```bash
       uv run python -m app.rag.evaluation.embedding.compare --models openai/text-embedding-3-small,gemini/text-embedding-004,local/BAAI/bge-m3,fake
       ```

