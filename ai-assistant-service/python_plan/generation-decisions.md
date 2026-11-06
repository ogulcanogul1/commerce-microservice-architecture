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

