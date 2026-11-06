# Generation Mimari Karar Günlüğü

Bu belge, RAG cevap üretimi (generation), atıf doğrulama (citation) ve abstain mekanizması geliştirilirken alınan mimari kararları ve gerekçelerini kayıt altına alır.

## Başlangıç Durumu ve Temel Kabuller
1. **Embedding Modeli ve Abstain Eşiği:** Kullanılan embedding modeli (`text-embedding-3-small` / fake) hâlâ geçici geliştirme aşamasındadır. Dense skoruna bağlı abstain kapısı eşiği (`RAG_MIN_DENSE_SCORE`) buna doğrudan bağlıdır ve Adım 8'deki `gate.py` ölçümüyle belirlenecektir.
2. **Corpus Boyutu ve Kalite Ölçümü:** Mevcut geliştirme korpusu 3 PDF (~8 chunk) ile sınırlıdır. Dolayısıyla elde edilecek generation eval kalite metrikleri ve eşikler geçicidir; gerçek geniş korpus eklendiğinde tekrar ölçülecektir.
3. **Test Başlangıç Sayısı (Baseline):** Generation geliştirmesine başlanmadan önce `uv run pytest -m "not integration"` koşulmuş ve **246 test passed** olarak kaydedilmiştir.
