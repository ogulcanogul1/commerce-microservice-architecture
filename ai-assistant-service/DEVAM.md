# DEVAM — AI Assistant Service Oturum Devir ve İlerleme Raporu

## Son Tamamlanan Aşama: Qdrant Vektör Veritabanı ve Hibrit Arama (qdrant.md)

`ai-assistant-service/python_plan/qdrant.md` planındaki Adım 0'dan Adım 8'e kadar tüm adımlar eksiksiz tamamlanmış, bellek içi (`:memory:`) ve sunucu modlarında doğrulanmış ve testleri yeşile çekilmiştir.

### Mimari Bileşenler ve Kapsam:
1. **Veri Modelleri ve Eşleme (`app/rag/vectorstore/`):**
   - `QdrantConfig` & `SearchHit`: Tip güvenli, dondurulmuş (frozen) konfigürasyon ve arama modeli.
   - `chunk_point_id`: `uuid5` tabanlı deterministik point kimliği üretimi.
   - `chunk_to_payload` & `payload_to_chunk`: Çift yönlü kayıpsız dönüşüm (`embedding_text` disk tasarrufu için hariç).
2. **Sparse Encoder (`sparse.py`):**
   - Deterministik `uint32` token indeksleme (`hashlib.blake2b(digest_size=4)`).
   - Corpus'tan bağımsız sabit `avgdl = 256.0` ile artımlı (incremental) BM25 TF ağırlıklandırması.
   - Qdrant `Modifier.IDF` ile sunucu taraflı BM25 IDF hesaplama.
3. **QdrantStore (`store.py`):**
   - Çift vektörlü (`dense` Cosine + `sparse` BM25) dinamik koleksiyon yönetimi (`{prefix}__{model}_{dim}`).
   - Boyut uyuşmazlığında sessiz ezme yerine fail-fast koruması.
   - Batch upsert ve `delete_stale` ile "upsert-then-delete" veri bütünlüğü garantisi.
4. **Arama ve Retriever Adaptörü (`search.py`, `retriever.py`):**
   - `search_dense`, `search_sparse` ve sunucu taraflı RRF hibrit füzyon (`search_hybrid`).
   - `QdrantRetriever`: Projenin standart `Retriever` protokolüne tam uyumlu adaptör.
5. **Parmak İzi ve Incremental Sync (`sync.py`):**
   - Yapısal SHA-256 içerik parmak izi (`doc_hash`): Element metinleri, sayfa/tip bilgileri, parser sürümü ve chunking ayarları.
   - İkinci sync koşusunda embedder çağrısı 0 (skipped) ile sıfır API maliyeti.
   - CLI arayüzü (`--docs-dir`, `--dry-run`, `--prune`).
6. **Parite Değerlendirmesi (`parity.py`):**
   - In-Memory (`DenseRetriever`, `HybridRetriever`) vs Qdrant (`QdrantRetriever`).
   - Dense sıralama farkı: 0 soru (%100 matematiksel eşleşme).
   - Hybrid Hit@3 farkı: 0.0 soru (tam parite).
7. **RAG Arama API (`app/api/search.py`):**
   - `POST /rag/search`: `query` (1..1000 karakter, boşluk korumalı), `k` (1..20), `mode` ('dense', 'sparse', 'hybrid'), `source_file` filtresi.
   - FastAPI `lifespan` yöneticisi altında `app.state` entegrasyonu (import anında ağa bağlanmama).
   - Dahili hata ve IP/URL sızdırmayan 503 ve 422 hata yönetimi.

---

### Beklenmeyen Bulgular ve Mühendislik İçgörüleri:
1. **Rust SIMD Floating-Point Tie (Kayan Nokta Eşitliği):** Soru Q03'te NumPy skorları `0.2331262` ve `0.2331262` (fark 0.0) olan iki chunk'ta Python NumPy kararlı sıralaması indeks sırasını (indeks 5, indeks 7) tercih ederken; Qdrant'ın Rust motoru SIMD vektör çarpımında `2e-8` ULP farkı (`0.23312622` vs `0.23312619`) hesaplamıştır. Bu durum, pratikteki benzerlik eşitliklerinin değerlendirme metriklerinde yanıltıcı olmaması için `1e-4` eşiğinde tie-breaker mantığı ile çözülmüştür.
2. **Local Mode (`:memory:`) Payload Index Uyarısı:** Qdrant yerel bellek modu vektör aramalarını ve RRF füzyonunu tam olarak desteklerken, payload indeksleri sunucu gerektirir. Birim testlerin Docker gerektirmeden tam hızda çalışabilmesi için local mode uyarısı güvenle ele alınmıştır.
3. **Korpus Doygunluğu (Corpus Saturation):** Test korpusu 3 PDF / 8 chunk'tan oluştuğu için k=5 sorgularında Hit@5 yapısal olarak %100'e doymaktadır. Raporlama aracı bu durumu otomatik algılayıp uyarı basacak şekilde yapılandırılmıştır.

---

### Doğrulama ve Test Özeti:
- **Toplam Birim Testi:** 231 test (tümü yeşil, Docker veya harici ağ gerektirmez).
- **Test Süresi:** ~23 saniye (`uv run pytest -m "not integration"`).

---

## Sıradaki İş (Next Step):
- **Aşama 4: Generation — kaynaklı cevap üretimi, citation doğrulama, abstain, `POST /rag/answer` ve generation eval.**
  - Plan: `python_plan/generation.md` (Adım 0–9). Karar günlüğü: `python_plan/generation-decisions.md` (Adım 0'da açılır).
  - Reranker bu aşamadan **sonraya** alındı: 8 chunk'lık corpus'ta Hit@5 doygun, reranker'ın faydası ölçülemez. Generation eval seti ve büyük corpus geldikten sonra ayrı planla ele alınacak.
