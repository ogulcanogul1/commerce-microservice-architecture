# DEVAM — AI Assistant Service Oturum Devir ve İlerleme Raporu

## Tamamlanan Aşama: Reranker Altyapısı, İki Aşamalı Arama ve A/B Ölçüm Çerçevesi (`python_plan/reranker.md`)

`ai-assistant-service/python_plan/reranker.md` planındaki Adım 0'dan Adım 8'e kadar tüm adımlar eksiksiz tamamlanmış, Docker veya harici ağ gerektirmeden ağsız modda 533 birim test ile doğrulanmış ve adım adım commitlenmiştir. Karar günlüğü `python_plan/rerank-decisions.md` dosyasına kaydedilmiştir.

---

### Mimari Bileşenler ve Kapsam:

1. **Reranker Protokolü ve Veri Modelleri (`app/rag/rerank/models.py`, `base.py`):**
   - `@runtime_checkable` `Reranker` protokolü: `rerank(query, hits, top_n) -> list[RerankResult]`.
   - `RerankResult`: `frozen=True` Pydantic v2 modeli (`hit`, `new_score`, `old_score`, `original_rank`, `metadata`).
   - `RerankError`: Reranker istisna sınıfı. Hatalı sıralama veya boş liste durumları `validate_rerank_results()` ile doğrulanır.

2. **Reranker Sağlayıcıları (`app/rag/rerank/`):**
   - Tüm sağlayıcılar (`FakeReranker`, `CrossEncoderReranker`, `CohereReranker`) açıkça `Reranker` arayüzüne bağlıdır.
   - `FakeReranker`: Kelime örtüşmesi (Jaccard-benzeri) veya enjekte edilen skorlarla çalışan deterministik, ağsız test motoru.
   - `CrossEncoderReranker`: Varsayılan `BAAI/bge-reranker-v2-m3`. Bellek ve thread güvenliği için `threading.Lock` ile korunan lazy model yüklemesi ve senkronize `predict()`.
   - `CohereReranker`: `httpx` üzerinden Cohere v2 API (`/v2/rerank`, `rerank-v3.5`). 429/5xx hatalarında 1 kez üstel geri çekilme, 4xx iş hatalarında fail-fast. Loglarda ve hata mesajlarında API key sızdırılmaz.

3. **Fabrika, Uygulama ve Retriever Adaptörü (`app/rag/rerank/factory.py`, `apply.py`, `retriever.py`):**
   - `build_reranker_from_settings()` ve `get_reranker()`: Ayarlardan reranker nesnesi üretimi.
   - `rerank_hits()`: Güvenli rerank yürütücüsü. Üretimde `RAG_RERANK_FAIL_OPEN=True` ile hata anında fallback olarak ilk $k$ hibrit sonucunu döner; değerlendirme modunda (`fail_open=False`) sessiz bozulmayı önlemek için hatayı yükseltir.
   - `RerankingRetriever`: `Retriever` protokolünü (`retrieve()`) uygulayan adaptör sınıfı. Değerlendirme çatısıyla sıfır sürtünmeyle çalışır.

4. **RagAnswerService ve Yaşam Döngüsü Entegrasyonu (`app/rag/generation/service.py`, `app/main.py`):**
   - `retrieve_with_rerank()`: İki aşamalı getirme (aday havuzu -> reranker -> top_k).
   - `RetrievalOutcome` ve `RagAnswer.rerank_status`: `disabled`, `applied`, `fallback_error`, `fallback_timeout`, `bypassed_insufficient_hits`.
   - Lifespan: Başlangıçta reranker hazır bulunur; kapanışta `close()` temizliği yapılır. `RAG_RERANK_ENABLED=False` iken sıfır çalışma zamanı yükü.

5. **Retrieval ve Generation A/B Değerlendirme Çerçevesi (`app/rag/evaluation/rerank/`):**
   - `compare.py`: CLI retrieval karşılaştırıcısı (`--reranker`, `--rerank-model`, `--candidates`, `--top-k`). `first_correct_rank`, `classify_flips`, doyum (saturation) ve tavan (ceiling) uyarıları.
   - `run.py --rerank`: Generation değerlendirme çalıştırıcısına fail-closed reranker bayrakları ve rerank durum istatistikleri.
   - `gate.py --rerank`: Dense skor ile en üst rerank skorunu yan yana ölçen analizör. Abstain eşiğini bozmaz.
   - `reports_diff.py`: İki generation raporu arasındaki metrik farklarını (`overall`, `answerable`, `unanswerable`), flip analizini, yeni halüsinasyon (`new_hallucination_queries`) ve gürültü uyarılarını CLI tablosu olarak sunar.

---

### Doğrulama ve Test Özeti:
- **Toplam Birim Testi:** **533 test** (Tümü passed, 7 deselected, 0 failure).
- **Test Süresi:** ~26 saniye (`uv run pytest -m "not integration"`).
- **Ağ ve Docker Bağımsızlığı:** Tüm rerank birim testleri (Fake, CrossEncoder mock, Cohere MockTransport, Service, Compare, Diff) harici ağ ve model indirme gerektirmeden çalışır.

---

### Sıradaki Aşama ve Gelecek Oturumlar İçin Notlar:
1. **Aşama 7 / Adım 9: Corpus Büyütme ve Canlı Reranker Karar Koşusu:**
   - Mevcut 3 dokümanlık (~8 chunk) toy corpus aday havuzu (k=20) için doyuma ulaştığından (`saturation warning`), doküman havuzu 10+ doküman ve 100+ chunk seviyesine çıkarılacaktır.
   - Ardından canlı Cross-Encoder ve Cohere eval koşuları yapılarak `RAG_RERANK_ENABLED` bayrağının prod varsayılanı kararlaştırılacaktır.
2. **Java Mikroservislerinde Tespit Edilen Açıkların Kapatılması (Ayrı Java İşi):**
   - `shipping-service`: `ShipmentResponse`'a `customerId` eklenmeli ve `/track/{trackingNumber}` uç noktasına sahiplik doğrulaması getirilmelidir.
   - `order-service`: `enforceOwnership` metodunda `X-User-Id` başlığı yoksa fail-fast (`401`/`403`) reddedilmelidir.
3. **Kalıcı Aksiyon Deposu:** Çok örnekli (multi-instance) üretim ortamı için `RedisPendingActionStore` uygulaması.
4. **Multi-Turn Sohbet Geçmişi:** Takip soruları için geçmiş taşıma ve query rewriting altyapısı.

### Yeni Oturumda İlk Okunacak Dosyalar:
1. `python_plan/rerank-decisions.md` (Reranker kararları, model özellikleri ve baseline sayıları)
2. `DEVAM.md` (Bu dosya)
3. `python_plan/agent-decisions.md` (Agent güvenlik ve karar ilkeleri)
4. `app/rag/rerank/` (Reranker çekirdek protokol ve uygulayıcıları)
5. `app/rag/evaluation/rerank/` (Rerank A/B ve diff araçları)
