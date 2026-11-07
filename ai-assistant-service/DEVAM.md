# DEVAM — AI Assistant Service Oturum Devir ve İlerleme Raporu

## Tamamlanan Aşama: Müşteri Destek Ajanı (Agent), Onaylı Aksiyonlar ve Güvenlik Paketi (`agent.md`)

`ai-assistant-service/python_plan/agent.md` planındaki Adım 0'dan Adım 10'a kadar tüm adımlar eksiksiz tamamlanmış, Docker veya harici ağ gerektirmeden ağsız modda 457 birim test ile doğrulanmış ve GitHub `main` dalına pushlanmıştır.

---

### Mimari Bileşenler ve Kapsam:

1. **LLM Tool Round-Trip Desteği (`app/llm/`):**
   - OpenAI/Local: `role="assistant", tool_calls=[...]` ve `role="tool", tool_call_id="..."`.
   - Anthropic Claude: `tool_use` blokları ve ardışık `tool_result` bloklarının tek user mesajında birleştirilmesi.
   - Google Gemini: `Part.from_function_call` ve `Part.from_function_response` tek `role="user"` altında birleştirme.
   - `FakeLLMProvider`: Scripted tool çağrıları ile ağsız ve deterministik test.

2. **Güvenlik Bağlamı (`app/core/security.py`):**
   - API Gateway'in ilettiği `X-User-Id` başlığından doğrulanmış `RequestContext` üretimi (UUIDv4 denetimi, `401 Unauthorized`).
   - `require_gateway_secret` ile `hmac.compare_digest` doğrudan erişim koruması (`403 Forbidden`).

3. **Downstream Mikroservis İstemcileri (`app/clients/`):**
   - `OrderClient` ve `ShippingClient` sınıfları. GET isteklerinde 1 kez otomatik retry, POST (iptal) işlemlerinde 0 retry.
   - `X-User-Roles` başlığı admin bypass açığını engellemek için downstream'e iletilmez.
   - `OrderView` ve `ShipmentView` PII filtreleme (adres ve alıcı bilgileri dış LLM'e sızdırılmaz). Path injection regex kontrolü (`_validate_order_number`).

4. **Tool Çatısı ve Okuma Araçları (`app/agent/tools/`):**
   - `get_order`, `list_my_orders`, `get_shipment`, `search_policy`, `request_order_cancellation`, `request_support_ticket`.
   - `extra="forbid"` ile modelden kimlik argümanı kabul edilmez (`ToolContext.user_id` kullanılır).
   - `render_for_model`: Indirect prompt injection etiket kaçırma (`<arac_sonucu>` -> `‹arac_sonucu›`) ve 2000 karakter sınırı.
   - 404 ve 403 hataları ID tarama saldırılarını önlemek için genel "Sipariş bulunamadı." metnine eşlenir.
   - Kargo sorgulaması doğrudan takip numarası ile yapılamaz; önce sipariş sahipliği doğrulanır.

5. **Onaylı Aksiyonlar ve Bilet Yayını (`app/agent/pending.py`, `executor.py`, `tickets.py`):**
   - `InMemoryPendingActionStore`: Thread-safe, 300 sn TTL, tek kullanımlık atomik `consume` (pop) ile replay koruması.
   - `ActionExecutor`: Onay anında sipariş durumunu yeniden sorgular, zaten iptal ise gereksiz POST yapmaz.
   - Unified Event Envelope formatında `LoggingTicketPublisher` ve `KafkaTicketPublisher` (`support.ticket.created`).

6. **AgentService ReAct Orkestrasyonu ve Grounding (`app/agent/service.py`, `grounding.py`, `prompt.py`):**
   - En fazla 4 adım, adım başına en fazla 3 araç.
   - `search_policy` çağrıldığında döngü terminal sonlanır ve RAG cevabı atıflarıyla birlikte birebir döner.
   - `check_reply_grounding`: Yanıttaki tüm rakam dizilerinin araç çıktılarında yer alması zorunludur. Uydurma sayılarda 1 düzeltme hakkı tanınır; tekrarlanırsa güvenli fallback döner.
   - Yapılandırılmış audit logu (`user_id_hash` sha256 12 karakter; soru metni, tool argümanı ve tutar sızdırılmaz).

7. **Agent HTTP API (`app/api/agent.py`) ve Lifespan Entegrasyonu (`app/main.py`):**
   - `POST /agent/chat`, `POST /agent/actions/{action_id}/confirm`, `POST /agent/actions/{action_id}/reject`.
   - `action_id` regex doğrulaması (`^[A-Za-z0-9_\-]{16,64}$`).
   - Tekil ve temiz yaşam döngüsü yönetimi; kapanışta açık HTTP ve Kafka istemcileri güvenle kapatılır.

8. **Güvenlik Test Paketi (`tests/agent/test_security_suite.py`):**
   - IDOR, prompt injection, replay, TTL, aksiyon çalma, durum yarışı, path traversal ve log hijyeni kapsayan 16 saldırgan senaryo (16/16 yeşil).

9. **Agent Değerlendirme Çerçevesi (`app/agent/evaluation/`, `eval/agent/cases.json`):**
   - 9 kategoride 39 vaka. CLI `--validate`, `ScenarioEnvironment` ve LLM-judge gerektirmeyen deterministik metrikler.
   - Markdown ve JSON raporlama (`eval/agent/reports/`).

---

### Doğrulama ve Test Özeti:
- **Toplam Birim Testi:** **457 test** (Tümü passed, 4 deselected, 0 failure).
- **Test Süresi:** ~26 saniye (`uv run pytest -m "not integration"`).
- **Ağ ve Docker Bağımsızlığı:** Tüm testler ağ bağlantısı veya Docker gerektirmeden bellek içi çalışır.

---

### Sıradaki Aşama ve Gelecek Oturumlar İçin Notlar:
1. **Java Mikroservislerinde Tespit Edilen Açıkların Kapatılması (Ayrı Java İşi):**
   - `shipping-service`: `ShipmentResponse`'a `customerId` eklenmeli ve `/track/{trackingNumber}` uç noktasına sahiplik doğrulaması getirilmelidir.
   - `order-service`: `enforceOwnership` metodunda `X-User-Id` başlığı yoksa fail-fast (`401`/`403`) reddedilmelidir.
2. **Kalıcı Aksiyon Deposu:** Çok örnekli (multi-instance) üretim ortamı için `RedisPendingActionStore` uygulaması.
3. **Multi-Turn Sohbet Geçmişi:** Takip soruları için geçmiş taşıma ve query rewriting altyapısı.
4. **Aşama 6: Reranker Değerlendirmesi:** Genişletilmiş korpus ile Cross-Encoder / FlashRank incelemesi.

### Yeni Oturumda İlk Okunacak Dosyalar:
1. `python_plan/agent-decisions.md` (Karar ve güvenlik ilkeleri)
2. `DEVAM.md` (Bu dosya)
3. `README.md` (Uç nokta curl örnekleri ve eval komutları)
4. `app/agent/service.py` ve `app/api/agent.py` (Asistan ana mantığı ve API)
