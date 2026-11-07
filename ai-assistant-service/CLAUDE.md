# CLAUDE.md - AI Assistant Service

Tüm mimari kurallar, araç tanımları, güvenlik politikaları ve port dağılımları için lütfen [AGENTS.md](AGENTS.md) ve repo kökündeki [AGENTS.md](../../AGENTS.md) dosyalarını inceleyin.

### Hızlı Kurallar Özeti
- **Dil ve Sürüm**: Python 3.12+ (Astral `uv` ortam yöneticisi).
- **Kimlik Yönetimi**: Müşteri kimliği ASLA kullanıcı mesajından veya model promptundan kabul edilmez. Yalnızca `X-User-Id` başlığı (`RequestContext`) kullanılır. Araç parametre şemalarında `customer_id` bulunamaz (`extra="forbid"`).
- **Yazma İşlemleri**: LLM doğrudan iptal veya yazma işlemi yapamaz. Yalnızca `PendingAction` oluşturur; işlem kullanıcının `POST /agent/actions/{action_id}/confirm` onayıyla yürütülür.
- **Kargo İzolasyonu**: `shipping-service` doğrudan takip numarasıyla sorgulanamaz. Önce `order-service` sahiplik doğrulaması yapılır, ardından sipariş ID ile kargo bilgisi çekilir.
- **Terminal Politika**: Şirket politikası sorularında `search_policy` çıktısı modele yeniden yazdırılmaz; doğrulanmış atıflarıyla birlikte doğrudan kullanıcıya iletilir.
- **PII Hijyeni**: Adresler ve serbest kullanıcı metinleri dış LLM bağlamına veya loglara ham haliyle aktarılmaz.
- **Reranker Bayrağı**: `RAG_RERANK_ENABLED` varsayılan `False`'tur. Üretimde fail-open (`RAG_RERANK_FAIL_OPEN=True`), eval koşularında kesinlikle fail-closed çalışır.
- **Birim Testleri**: Ağ veya Docker gerektirmeden `uv run pytest -m "not integration"` ile çalışır.
