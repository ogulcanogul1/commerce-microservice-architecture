# Qdrant Karar Günlüğü

Bu belge; kalıcı vektör veritabanı (Qdrant), koleksiyon şeması, hybrid arama, payload indeksleme, incremental sync ve arama API'sine dair verilen mimari kararları ve gerekçelerini kayıt altına alır.

---

## Adım Bazlı Kararlar

- **Adım 0 (Hazırlık ve Altyapı):**
  - **Geçici Embedding Modeli Bağlantısı:** Seçilen embedding modeli (`openai/text-embedding-3-small`, 1536 dim / 512 dim Matryoshka) `embedding-decisions.md` Adım 9 gereğince hâlâ **geçicidir (provisional)**. Qdrant koleksiyonu model sağlayıcısı, model adı ve boyutuna duyarlı dinamik adlandırma (`{prefix}__{provider}_{model}_{dim}`) ile açılacaktır. Model veya boyut değiştiğinde eski koleksiyon ile karışmadan yeni koleksiyona geçiş sağlanır.
  - **Local Mode (`:memory:`) Doğrulama Sonucu:** `qdrant-client` 1.20.0 yerel bellek modu (`QdrantClient(":memory:")`) test edilmiştir. Bellek içi modda named dense vectors (`Distance.COSINE`), named sparse vectors (`Modifier.IDF`), point upsert ve `query_points` ile `Prefetch` + `FusionQuery(fusion=Fusion.RRF)` tam olarak desteklenmektedir. Bu sayede tüm birim testler Docker ve ağ bağımlılığı olmadan izole bir şekilde `:memory:` üzerinde koşturulabilir. Yalnızca gerçek sunucu ve network entegrasyonunu doğrulayan testler `@pytest.mark.integration` ile ayrılacaktır.
  - **Docker & Port İzolasyonu:** Qdrant v1.20.0 imajı `docker-compose.yml` içerisine REST (6333) ve gRPC (6334) portları ile eklenmiş, kalıcı veri hacmi (`qdrant_data`) bağlanmıştır. Port tablosu güncellenmiştir.
- **Adım 1 (Config, ID ve Payload Eşlemesi):**
  - **Point ID Standardı (uuid5):** Qdrant'ın 16-hex string ID'leri kabul etmemesi nedeniyle, chunk ID'leri `uuid.uuid5(uuid.NAMESPACE_URL, chunk.id)` ile deterministik ve idempotent UUID string'e dönüştürüldü.
  - **Kayıpsız Payload & Disk Tasarrufu:** `chunk_to_payload` ve `payload_to_chunk` ile çift yönlü kayıpsız dönüşüm sağlandı. `embedding_text` türetilebilir alan olduğu için payload'dan hariç tutularak disk tasarrufu sağlandı; `doc_hash`, `embedding_model_id` ve `ingested_at` operasyonel metadata'ları eklendi.
  - **Dinamik Koleksiyon İsimlendirme:** `QdrantConfig.collection_name(embedder)` ile `{prefix}__{model_slug}_{dimensions}` kuralı uygulandı; model veya boyut değiştiğinde koleksiyonların çakışması önlendi.
- **Adım 2 (Sparse Encoder):**
  - **Deterministik uint32 Token İndeksleme (Karar 4):** Python'ın rastgele seed'e sahip `hash()` fonksiyonu yerine `hashlib.blake2b(digest_size=4)` kullanılarak süreçler arası değişmeyen kararlı `uint32` token indeksleri üretildi.
  - **Corpus'tan Bağımsız Sabit avgdl (Karar 3):** Doküman ekleme/güncellemelerde eski dokümanların sparse vektörlerinin bozulmaması (incremental sync uyumluluğu) için `avgdl = 256.0` sabiti kullanıldı. Doküman tarafında TF ve uzunluk cezası hesaplandı, IDF hesabı sunucu tarafına (`Qdrant Modifier.IDF`) bırakıldı.
  - **Yinelenen İndeks ve Sıralama Garantisi:** Qdrant gereksinimleri doğrultusunda sparse indeksler kesin artan sırada (`sorted`) düzenlendi; olası hash çakışmalarında ağırlıklar toplanarak tekilleştirildi. Boş/stopword metinler için boş vektör dönüldü.
- **Adım 3 (QdrantStore - Koleksiyon, İndeks ve Yazma):**
  - **Sorumluluk Ayrımı (Yalnızca Yazma/Yönetim):** Arama mantığı bu sınıfa dahil edilmedi; `QdrantStore` yalnızca koleksiyon oluşturma, boyut doğrulama, payload indeksleme ve CRUD işlemlerini üstlendi.
  - **Çift Vektörlü Koleksiyon Şeması (Named Vectors):** `dense` (`Distance.COSINE`) ve `sparse` (`Modifier.IDF`) alanları tanımlandı. Mevcut koleksiyon varsa vektör boyutu doğrulandı; uyuşmazlıkta sessizce ezmek yerine fail-fast ile `ValueError` fırlatıldı.
  - **Batching ve Idempotent Upsert:** `upsert_batch_size` dilimleriyle partili yazma sağlandı. `uuid5` sayesinde aynı chunk tekrar yazıldığında point sayısı değişmedi (idempotency).
  - **Upsert-then-Delete Güvencesi (Karar 7):** `delete_stale` metodu ile yalnızca hedef dosyanın güncel olmayan (`doc_hash != keep_doc_hash`) point'lerinin silinmesi garanti altına alındı; diğer dosyalara dokunulmadı.
- **Adım 4 (Arama ve Retriever Adaptörü):**
  - **Sunucu Taraflı RRF Hybrid Füzyon (Karar 2):** İstemci tarafı füzyon yerine, Qdrant'ın `query_points(prefetch=[dense, sparse], query=FusionQuery(fusion=Fusion.RRF))` API'si kullanıldı. Prefetch limiti `max(k * 4, 20)` olarak belirlendi; sorguda sparse token yoksa otomatik dense fallback uygulandı.
  - **Retriever Protokol Uyumu:** `QdrantRetriever` sınıfı mevcut `Retriever` protokolüne (`index`, `search`, `search_by_budget`) tam uyumlu yazıldı. Bütçe biriktirmede `select_chunks_by_budget` ortak yardımcısı kopyalanmadan yeniden kullanıldı.
  - **Filtre ve Uç Durum Yönetimi:** `source_file` ve `page_start/end` filtreleri `SearchFilter` ile izole edildi; boş sorgularda fail-safe olarak boş liste dönüldü. Mevcut tüm testlerin yeşil olduğu korundu.
