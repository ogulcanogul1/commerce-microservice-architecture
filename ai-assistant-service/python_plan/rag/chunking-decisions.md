# Chunking Tasarım Kararları Günlüğü

> [!NOTE]
> **Önemli Not (Sentetik / Ön Doğrulama Aşaması):**
> Aşağıdaki karar ve metrik çıkarımları, boru hattının ilk aşamasında hazırlanan 3 adet sentetik test PDF'i ve 42 soruluk prototip Golden Set üzerindeki ölçümlere dayanmaktadır. Kararlar "geçici / ön doğrulanmış" (provisional) niteliktedir. Gerçek e-ticaret kurumsal dokümanları (RAG veri kümesi) sisteme aktarıldığında benchmark deneyleri bu veri seti üzerinde yeniden çalıştırılacak ve kesin metrikler güncellenecektir.

Bu belge, chunking pipeline'ı kurulurken verilen eşik, parametre ve mimari kararların gerekçelerini belgeler.

## Adım 0 — Hazırlık
- Tokenizer olarak endüstri standardı `cl100k_base` (`tiktoken`) ve testler için harici bağımlılıksız deterministik `WhitespaceTokenizer` seçildi.
- Retrieval değerlendirmesi için embedding öncesi tarafsız ve hızlı doğrulama amacıyla BM25 (`rank-bm25`) seçildi.
- Rapor dizini (`eval/chunking/reports/`) git geçmişini kirletmemesi için `.gitignore`'a eklendi.

## Adım 1 — Modeller (ChunkingConfig & Chunk)
- `ChunkingConfig` değişmez (`frozen=True`) tanımlandı; `overlap_tokens < max_tokens` ve `min_tokens <= max_tokens` eşik kuralları doğrulandı.
- Deterministik chunk ID'si ve sweep karşılaştırmaları için 8 karakterlik `config_hash()` üretimi eklendi.
- LLM prompt metni (`text`) ile retrieval bağlam metni (`embedding_text` = `context_prefix + text`) ayrıldı.
- Matematiksel kapsama (coverage) güvencesi için `char_start` ve `char_end` ofsetleri zorunlu tutuldu.

## Adım 2 — Tokenizer Soyutlaması
- `Tokenizer` arayüzü `typing.Protocol` ile gevşek bağlı (loosely coupled) ve duck-typing uyumlu tasarlandı; `@runtime_checkable` ile çalışma zamanı doğrulaması sağlandı.
- Hızlı ve harici bağımlılıksız testler için regex tabanlı `WhitespaceTokenizer` eklendi.
- `TiktokenTokenizer` (`cl100k_base`) implementasyonunda, BPE bayt akışının çok baytlı Türkçe UTF-8 karakter sınırlarını bölmesini engellemek için bayt biriktirme (`byte_buffer`) ve Unicode karakter ofset hizalaması uygulandı.

## Adım 3 — Flatten ve Span Haritası
- `flatten()` ile doküman elementleri `\n\n` ile birleştirilirken her elementin koordinatları değişmez `Span` nesneleri olarak saklandı.
- Dilimlenen karakter aralıklarına (`[start, end)`) denk gelen elementleri ve sayfa/başlık metadata'larını bulmak için `bisect.bisect_right` ile $O(\log N)$ ikili arama kullanıldı.
- Başlık yolunda (`heading_path`), ingestion kuralı gereği başlığın kendisi yolda yer almadığından, dilim başında `HEADING` elementi varsa başlık metninin yola eklenmesi sağlandı.

## Adım 4 — Ortak Arayüz ve Fixed-Size Chunker
- Tüm chunker'ların uyması gereken `Chunker` protokolü (`name: str`, `chunk(doc) -> list[Chunk]`) tanımlandı.
- `FixedSizeChunker` baseline olarak kurgulandı; token indeksleri üzerinde `step = max_tokens - overlap_tokens` pencereleriyle metni içerikten bağımsız kesti.
- Metin sonundaki kalan token'lar overlap payına (`<= overlap_tokens`) eşit veya azsa, yalnızca tekrardan ibaret yeni chunk açılması engellendi.
- Sihirli string'lerin (magic strings) önüne geçmek ve tip güvenliğini sağlamak için `ChunkStrategy(StrEnum)` (`FIXED`, `RECURSIVE`, `STRUCTURE`) eklendi.

## Adım 5 — Türkçe Cümle Bölücü
- Saf offset tabanlı `split_sentences(text) -> list[tuple[int, int]]` fonksiyonu yazıldı.
- `Dr.`, `Prof.`, `vb.`, `sn.`, `No.`, `A.Ş.`, `Ltd.` gibi yaygın Türkçe kısaltmalar `ABBREVIATIONS` frozenset'iyle korundu.
- Ondalık sayılar (`3.5`), tarihler (`14.02.2026`) ve madde numaraları (`4.1`) nokta korumasına alındı.
- Türkçe büyük harfler (`Ç, Ğ, İ, Ö, Ş, Ü`) regex'e dahil edilerek cümle sınırları tespit edildi; ardışık dilimlerin metni %100 örtmesi sağlandı.

## Adım 6 — Recursive Chunker ve Strateji Paket Yapısı
- Chunker sınıfları daha modüler bir mimari için `app/rag/chunking/strategies/` alt paketine taşındı.
- `RecursiveChunker` separator merdiveni (`\n\n` -> `\n` -> cümle -> boşluk -> token) ile atomik birim çıkarma mantığı kuruldu.
- Greedy birleştirme ve tam birim (parça bölmeyen) overlap mantığı uygulandı.
- `min_tokens` altındaki son küçük chunk'ların önceki chunk ile bütçeyi (`max_tokens`) aşmadığı sürece birleştirilmesi sağlandı.

## Adım 7 — Structure-Aware Chunker
- `StructureAwareChunker` ile doküman `HEADING` sınırlarına göre bölümlendi; chunk'ların bölüm dışına taşması engellendi.
- `context_prefix` token bütçesinden düşülerek embedding boyutu garantilendi.
- Bütçeyi aşan tablolarda başlık satırı ve `|---|` ayırıcısının tüm alt parçalara otomatik kopyalanması sağlandı.
- `min_tokens` altındaki küçük kardeş bölümler aynı üst başlığa sahipse birleştirildi.
- İçeriği olmayan başlıklar için yetim başlık koruması (orphan heading prevention) uygulandı.

## Adım 8 — Factory ve Ortak Sözleşme Testleri
- `get_chunker` fabrika fonksiyonu ile strateji nesnesi üretimi tek bir noktada toplandı; geçersiz strateji durumunda açıklayıcı hata verildi.
- 3 chunker için parametrik (`pytest.mark.parametrize`) 8 sözleşme kuralı (boş metin yok, token limiti, kapsama, indeks artışı, sayfa aralığı, determinizm, tekil ID, boş doküman güvenliği) 25 test ile doğrulandı.

## Adım 9 — Intrinsic (İçsel) Değerlendirme Metrikleri
- Arama gerektirmeyen, doğrudan chunk çıktısını ölçümleyen `chunk_stats()` fonksiyonu ve `ChunkStats` Pydantic modeli geliştirildi.
- Token dağılımı (ortalama, p50, p95, min, max, under_min_ratio) ve overlap fazlalık maliyeti (`redundancy`) formülize edildi.
- Parçalanma hasarını ölçmek için `sentence_cut_ratio` (cümle ortasından kesilme), `table_split_ratio` (bölünen tablolar), `table_headless_chunks` (başlığı kopan tablo parçaları) ve `orphan_heading_ratio` (yetim kalan başlıklar) heuristikleri uygulandı.

## Adım 10 — Golden Set Veri Seti ve Eşleştirme Normalizasyonu
- Chunker kıyaslamalarında kimlik (`chunk_id`) yerine ham kanıt metni (`evidence`) eşleşmesi esası benimsendi.
- Türkçe-duyarlı `normalize_for_match()` ile `İ/i` ve `I/ı` küçük harf dönüşümleri ile Unicode NFC ve boşluk normalizasyonu yapıldı.
- 6 zafiyet kategorisinde (`single_fact`, `exception`, `table_lookup`, `table_cross_page`, `cross_page_sentence`, `heading_dependent`) 42 soruluk `golden_set.json` ve 3 referans PDF dokümanı hazırlandı.
- `--validate` CLI komutu ile soru kanıtlarının ingestion çıktılarındaki varlığı otomatik doğrulandı.

## Adım 11 — BM25 Tabanlı Retrieval Değerlendirmesi
- Embedding öncesi chunker kıyaslamalarını bağımsız ve maliyetsiz kılmak için `Retriever` protokolü ve `BM25Retriever` (`rank_bm25`) kuruldu.
- Kanıtın tek bir chunk içinde kalıp kalmadığını ölçen `evidence_intact` ve `evidence_fragmented` metrikleri tanımlandı.
- Sıralama başarımı için `Hit@1`, `Hit@3`, `Hit@5` ve `MRR` formülleri soru ve kategori bazlı uygulandı.
- Büyük chunk stratejilerinin haksız bağlam avantajını dengelemek için `search_by_budget()` (sabit token bütçesi modu) eklendi.

## Adım 12 — Karşılaştırma Runner'ı ve Ablation Deneyleri
- `compare.py` ile `Fixed-Size`, `Recursive` ve `Structure-Aware` stratejilerini `max_tokens` (200, 300, 350) ve `overlap` taramalarıyla adil kıyaslayan runner kuruldu.
- Breadcrumb (`include_breadcrumb`) açık ve kapalı halleriyle başlık önekinin aramadaki saf etkisi ölçüldü.
- Deneyler sonucunda `max_tokens=200, overlap=0` durumunda Fixed-Size'ın evidence intact oranının %85.7'ye düştüğü, cümle kesilme hasarının %33.3'e fırladığı ve Hit@3 skorunun çöktüğü kanıtlandı; Recursive ve Structure-Aware'in yapı koruyucu üstünlüğü doğrulandı.
- Üretilen Markdown ve JSON raporları `eval/chunking/reports/` altında otomatik arşivlendi.

## Adım 13 — Nihai Mimari Kararlar ve Devir (Ön Değerlendirme)
1. **Structure-Aware vs Recursive:** Structure-Aware chunker, tablolar bölündüğünde sütun başlıklarını her alt parçaya kopyalar ve doküman hiyerarşisine (`HEADING` sınırlarına) göre doğal bölümler oluşturur. Bu sayede cümle kesilme oranını (%0.0) ve anlamsal dağılmayı engeller. (Not: Nihai başarım oranları gerçek politika dokümanları aktarıldığında güncellenecektir).
2. **Overlap Etkisi:** Dar pencere bütçelerinde (`max_tokens=200`) overlap olmaksızın çalışan kayan pencerede (`FixedSize`) cümle hasarı %33.3'e fırlayıp Hit@1 skoru %69'a gerilerken; Recursive overlap veya Structure-Aware doğal sınır koruma yaklaşımları metin bütünlüğünü korumuştur.
3. **Varsayılan Chunker ve Token Bütçesi:** E-ticaret belgelerindeki yoğun tablo ve hiyerarşik maddeler nedeniyle platformun varsayılan motoru olarak `StructureAwareChunker` (`DefaultChunker`) seçildi. Varsayılan parametreler: `max_tokens=300`, `min_tokens=60`, `include_breadcrumb=True` (Structure-Aware için kayan overlap geçerli değildir, semantik bölüm sınırları kullanılır).
4. **Embedding Modeli ve Context Window Uyumu:** Seçilen varsayılan model olan `text-embedding-3-small` (`max_input_tokens=8191`), `ChunkingConfig(max_tokens=300)` ve breadcrumb önekleri ile üretilen maksimum korpus chunk boyutu (< 350 token) ile %100 uyumludur; en dar limitli model olan `multilingual-e5-small` (512 token) dahil hiçbir model sınırını aşmamaktadır (`validate_chunks_fit: all_fit=True`).















