# Generation Mimari Karar Günlüğü

Bu belge, RAG cevap üretimi (generation), atıf doğrulama (citation) ve abstain mekanizması geliştirilirken alınan mimari kararları ve gerekçelerini kayıt altına alır.

## Başlangıç Durumu ve Temel Kabuller
1. **Embedding Modeli ve Abstain Eşiği:** Kullanılan embedding modeli (`text-embedding-3-small` / fake) hâlâ geçici geliştirme aşamasındadır. Dense skoruna bağlı abstain kapısı eşiği (`RAG_MIN_DENSE_SCORE`) buna doğrudan bağlıdır ve Adım 8'deki `gate.py` ölçümüyle belirlenecektir.
2. **Corpus Boyutu ve Kalite Ölçümü:** Mevcut geliştirme korpusu 3 PDF (~8 chunk) ile sınırlıdır. Dolayısıyla elde edilecek generation eval kalite metrikleri ve eşikler geçicidir; gerçek geniş korpus eklendiğinde tekrar ölçülecektir.
3. **Test Başlangıç Sayısı (Baseline):** Generation geliştirmesine başlanmadan önce `uv run pytest -m "not integration"` koşulmuş ve **246 test passed** olarak kaydedilmiştir.

## Adım 1 Kararları — LLM Katmanı Eki
1. **ClaudeProvider Varsayılan Modeli:** `ClaudeProvider` varsayılan modeli `claude-3-5-sonnet-20241022` olarak korundu; geriye dönük uyumluluk bozulmadı. İhtiyaç halinde model id'si `RAG_LLM_MODEL` ayarıyla dinamik olarak değiştirilir.
2. **Factory Alias Desteği:** `LLMFactory.get_provider` metoduna docstring ile uyumlu olarak `"anthropic"` (Claude için) ve `"ollama"` (Local için) takma adları eklendi.
3. **Model İsmi Dinamikliği:** `LLMFactory.get_provider` metoduna `model_name` parametresi eklendi ve tüm sağlayıcı sınıflarına geçirildi.
4. **TokenUsage & Ağsız Test:** `FakeLLMProvider` kelime bazlı deterministik token sayımı ve çağrı geçmişi (`calls`) kaydıyla `tests/llm/` altında 12 ağsız testle doğrulandı. Toplam test sayısı 258'e yükseldi.

## Adım 2 Kararları — PII Maskeleme
1. **PII Kapsamı ve Algoritmik Doğrulama:**
   - `tckn`: 11 hane, ilk hane 0 değil ve resmi 10./11. hane checksum kuralları sağlandığında `[TCKN]` ile maskelenir. Checksum tutmayan 11 haneli sayılar (sipariş no vb.) bilerek serbest bırakılır.
   - `card`: 13–19 hane arası tireli/boşluklu kartlar Luhn (mod 10) algoritması doğrulandığında `[KART]` ile maskelenir.
   - `iban`: `TR` ile başlayan 24 haneli hesap numaraları `[IBAN]` ile maskelenir.
   - `phone`: `+90` ve `0` ile başlayan 10 haneli `5xx` TR mobil telefon formatları `[TELEFON]` ile maskelenir.
   - `email`: Standart e-posta formatları `[EPOSTA]` ile maskelenir.
2. **İş Mantığı Korunumu:** Sipariş numaraları, para tutarları, süreler ("14 gün") ve tarihler soru bağlamını yok etmemek için maskeleme dışı bırakılmıştır.
3. **Çakışma ve İndeks Yönetimi:** Varlıklar non-overlapping `_PIISpan` modeli ile tespit edilip sağdan sola değiştirilerek karakter offset kaymaları önlenmiştir.
4. **Test Sayısı:** `tests/core/test_pii.py` altında 9 yeni test eklendi; toplam test sayısı 267'ye yükseldi.

## Adım 3 Kararları — Modeller ve Context Builder
1. **Citation İndeksi ve Blok Numaralama:** Modeller `[1]`, `[2]` gibi 1'den başlayan ve ardışık artan basit referans numaraları görür; sunucu tarafında bu numaralar `ContextBlock` ve `Citation` modelleri ile gerçek `chunk.id`, `source_file`, `page_start/end` ve `heading_path` ile eşleştirilir.
2. **Context Bütçesi ve Başlık Maliyeti:** Bir bloğun token maliyeti hem başlık satırını hem de chunk metnini kapsar (`cost = count(header) + count(text)`). İlk blok tek başına bütçeyi aşsa bile bilgi kaybını önlemek için içeri alınır ve uyarı loglanır.
3. **Indirect Prompt Injection Savunması:** Doküman metinleri veya başlıkları içinde yer alan `<kaynaklar>` ve `</kaynaklar>` etiketleri `‹kaynaklar›` ve `‹/kaynaklar›` olarak kaçırılarak modelin prompt yapısını manipüle etmesi engellenmiştir.
4. **Tekilleştirme:** Aynı `chunk.id`'ye sahip yinelenen arama sonuçları elenir.
5. **Test Sayısı:** `tests/generation/test_context.py` altında 7 yeni test eklendi; toplam test sayısı 274'e yükseldi.

## Adım 4 Kararları — Prompt Tasarımı
1. **Sistem Promptu ve Grounding:** Modelin yalnızca `<kaynaklar>` etiketleri içindeki verileri kullanması, dış bilgi katmaması ve kaynaklarda cevap yoksa yalnızca `BULUNAMADI` yazması kuralı kesinleştirildi.
2. **Sayıların Formatı:** Modelin sayıları ve süreleri yazıyla ("on dört") değil kaynaktaki gibi rakamla ("14") yazması zorunlu kılındı; bu kural deterministik sayı doğrulamasını (`number_not_in_source`) mümkün kılar.
3. **Retry Geri Bildirimi ve Bütçe:** Doğrulama hatalarında modele gönderilen düzeltme mesajı en fazla 5 maddeyi listeler; 5'ten fazla sorun varsa `...ve N sorun daha` şeklinde özetlenerek context token israfı önlenir.
4. **Test Sayısı:** `tests/generation/test_prompt.py` altında 3 yeni test eklendi; toplam test sayısı 277'ye yükseldi.

## Adım 5 Kararları — Citation Doğrulama
1. **Cümle Bölücü ve Kısaltmalar:** Cümleler `.`, `!`, `?` işaretlerinden bölünür; ancak yaygın Türkçe kısaltmalar (`vb.`, `vs.`, `örn.`, `s.`, `Md.`, `No.`, `Dr.`, `Prof.`), ondalık/binlik sayılar (`1.000`, `2,5`) ve tarihler (`14.05.2026`) bölünmez. Noktadan hemen sonra gelen atıf grupları (`. [1][2]`) ait olduğu önceki cümleye bağlanır.
2. **Deterministik Doğrulama (3 Kontrol):**
   - `uncited_sentence`: Cevabın her cümlesinde en az bir geçerli atıf bulunmalıdır.
   - `invalid_citation`: Atıf yapılan kaynak `1..len(blocks)` sınırları içinde olmalıdır.
   - `number_not_in_source`: Cümledeki her rakam grubu (`\d+`), cümlenin atıf yaptığı kaynakların metninde veya başlığında geçmelidir.
3. **Doğrulama Önceliği:** Bir cümlede `invalid_citation` varsa o cümle için sayı kontrolü atlanır; çünkü olmayan bir kaynağın metni karşılaştırılamaz.
4. **Sayı Kontrol Sınırı:** Kontrol rakam dizileri (`\d+`) üzerinden yapılır; yazıyla yazılmış sayılar ("on dört") yakalanamaz (bu sınır kabul edilmiştir).
5. **Abstain Tespiti:** Cevabın herhangi bir yerinde `bulunamadı` ifadesinin geçmesi kesin abstain sayılır (kısmi cevap + bulunamadı karışımı güvensizdir).
6. **Test Sayısı:** `tests/generation/test_citations.py` altında 9 yeni test eklendi; toplam test sayısı 286'ya yükseldi.





