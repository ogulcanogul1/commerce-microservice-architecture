# Reranker Karar Günlüğü (Decisions Log)

## 1. Genel Durum ve Temel Kararlar
- **Corpus Durumu:** 3 PDF ≈ 8 chunk. Aday havuzu (`top_candidates=20`) tüm korpusu kapsadığı için reranker açma/kapama nihai kararı büyük korpus (≈ 10 doküman, ≈ 100 chunk) gelince verilecektir (Adım 9).
- **Varsayılan Durum:** Reranker varsayılan olarak **KAPALI** (`RAG_RERANK_ENABLED=False`). Kapalıyken sistem bugünkü performans ve davranışıyla birebir aynı çalışır; hiçbir ekstra import ve model yüklemesi yapılmaz.
- **Fail-Open (Üretim) vs. Fail-Closed (Eval):**
  - Üretimde (`RAG_RERANK_FAIL_OPEN=True`): Reranker zaman aşımına uğrar veya hata verirse sistem durmaz, uyarı loglanır, orijinal retrieval sırasıyla ilk `k` sonuç döndürülür ve durum `rerank_status="failed"` olarak işaretlenir.
  - Değerlendirmede (`eval` / `compare.py` / `run.py`): Her zaman `fail_open=False` çalışır; bir reranker hatası gizlenip temel çizgi gibi görünmesin diye hata derhal fırlatılır.
- **Birim Test Sayıları:**
  - Baseline: 471 passed, 5 deselected
  - Tamamlanma (Adım 0 → 8): 533 passed, 7 deselected (+62 yeni test, sıfır gerileme).

## 2. Sağlayıcılar ve Model Detayları
1. **Yerel Model (`CrossEncoderReranker`):**
   - Kütüphane: `sentence-transformers` (opsiyonel bağımlılık grubu: `local-embedding`).
   - Varsayılan Model: `BAAI/bge-reranker-v2-m3` (Çok dilli, Türkçe desteği güçlü, 512 token max context).
   - Tembel Yükleme: Model kurucuda yüklenmez, ilk `rerank()` çağrısında `threading.Lock` altında bir defa yüklenir.
   - Eşzamanlılık Güvenliği: `predict` çağrıları PyTorch güvenliği için `threading.Lock` ile korunur.
   - Zaman Aşımı: `RAG_RERANK_TIMEOUT_SEC` yerel CPU model çağrılarında kesme (interrupt) yapılamadığı için uygulanmaz.
2. **API Tabanlı Model (`CohereReranker`):**
   - Doğrudan REST çağrısı: Ek SDK kütüphanesi eklenmeden `httpx` ile `POST https://api.cohere.com/v2/rerank` uç noktası kullanılır.
   - Varsayılan Model: `rerank-v3.5`.
   - Yeniden Deneme (Retry): 429 ve 5xx hatalarında 1 kez kısa aralıkla tekrar denenir (toplam 2 deneme). 401, 403, 400 gibi istemci hatalarında fail-fast edilir.
   - Zaman Aşımı: `RAG_RERANK_TIMEOUT_SEC` (varsayılan 10.0 sn) HTTPX istemcisine bağlanır.
   - Güvenlik: Hata mesajlarında ve loglarda API anahtarı, soru metni ve doküman içerikleri asla yer almaz.

## 3. Reranker'a Verilen Metin Kararı
- Reranker'a doküman metni olarak `chunk.embedding_text` (başlık hiyerarşisi + metin) verilir. Başlık yolu (`İade > Süre`) bağlamsal alaka için kritik bilgi taşır.
- Sorgu olarak `retrieve` metoduna gelen **maskelenmiş** (`mask_pii`) soru iletilir; müşteri PII verisi dış sağlayıcıya açık gitmez.

## 4. Abstain Kapısı Kararı
- Abstain kapısı (`min_dense_score`), önceden olduğu gibi `search_dense(k=1)` cosine skoruna bakmaya devam eder.
- Rerank skorları cosine ile aynı ölçekte olmadığı için kapı eşiği reranker'a bağlanmaz. `gate.py --rerank` aracı yalnızca skor dağılımını gözlemlemek için kullanılır; eşik önermez.

## 5. Dış Sağlayıcıya Veri ve Gizlilik Notu
- Cohere kullanıldığında soru ve politika chunk metinleri harici API'ye gider. PII maskelemesi aktif olsa da şirket içi dokümanların dışarı çıkmasını istemeyen ortamlar için yerel `CrossEncoderReranker` tam bir alternatiftir.

## 6. Kod Değişiklikleri Özeti
- `app/rag/rerank/`: `models.py`, `base.py`, `fake.py`, `cross_encoder.py`, `cohere.py`, `factory.py`, `apply.py`, `retriever.py` modülleri eklendi.
- `app/rag/generation/models.py`: `GenerationConfig`'e rerank alanları, `RetrievalOutcome` modeli ve `RagAnswer.rerank_status` eklendi.
- `app/rag/generation/service.py`: `retrieve_with_rerank()` ve opsiyonel `reranker` enjeksiyonu eklendi.
- `app/main.py`: Başlangıçta güvenli `build_reranker_from_settings()` eklendi.
- `app/rag/vectorstore/`: **Hiçbir dosya değiştirilmedi**, sadece kullanıldı.
- `app/agent/`: **Hiçbir dosya değiştirilmedi**.

## 7. Sonraya Bırakılanlar (Backlog / Adım 9)
- Corpus genişletildikten sonra (≈ 10 doküman, ≈ 100 chunk) Adım 9 karar prosedürünün işletilmesi.
- `/rag/search` uç noktasında rerank desteği.
- Rerank skoruyla abstain kapısı (dağılımlar yeterince ayrışırsa).
- LLM tabanlı reranking ("modele sırala dedirtmek").
- Reranker sonuç önbelleklemesi (caching).
