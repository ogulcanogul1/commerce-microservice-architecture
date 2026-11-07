# DEVAM — AI Assistant Service Oturum Devir ve İlerleme Raporu

## Tamamlanan Aşama: RAG Cevap Üretimi (Generation), Atıf Doğrulama ve Abstain Mekanizması (`generation.md`)

`ai-assistant-service/python_plan/generation.md` planındaki Adım 0'dan Adım 9'a kadar tüm adımlar eksiksiz tamamlanmış, Docker veya harici ağ gerektirmeden ağsız modda 324 birim test ile doğrulanmış ve GitHub `main` dalına pushlanmıştır.

---

### Mimari Bileşenler ve Kapsam:

1. **LLM Katmanı ve TokenUsage Eki (`app/llm/`):**
   - `TokenUsage(input_tokens, output_tokens)` modeli ve `BaseLLMProvider.generate`'e `max_tokens` desteği.
   - OpenAI, Claude, Gemini ve Local sağlayıcılarında tam token ve kullanım eşlemesi.
   - `FakeLLMProvider`: Kelime bazlı deterministik token sayımı, çağrı kaydı (`calls`), sequential/responder desteği ve ağsız test ortamı.

2. **PII Maskeleme (`app/core/pii.py`):**
   - TCKN (resmi 10./11. hane algoritması ile tam checksum kontrolü).
   - Kredi Kartı (13–19 hane arası Luhn mod-10 algoritması).
   - IBAN (`TR` + 24 hane), E-posta ve Mobil Telefon (`05xx`, `+905xx`).
   - Non-overlapping span tespiti ve sağdan sola yer değiştirme; sipariş numaraları ve iş süreleri ("14 gün") korunur.

3. **Modeller ve Context Builder (`app/rag/generation/`):**
   - `ContextBlock`, `Citation`, `ValidationIssue`, `RagAnswer`, `GenerationConfig`.
   - `build_context`: `[1]`, `[2]` şeklinde blok numaralama, sayfa/başlık bilgisi, indirect prompt injection koruması (`<kaynaklar>` etiket kaçırma) ve token bütçesi (`header + text`).

4. **Sistem Promptu ve Retry Mekanizması (`prompt.py`):**
   - Grounding kuralı: Yalnızca verilen kaynakları kullanma, harici bilgi katmama, bilgi yoksa tek başına `BULUNAMADI` yazma.
   - `build_retry_messages`: Doğrulama hatalarında bulunan ilk 5 sorunu modele iletip düzeltme talep etme.

5. **Atıf ve Sayı Doğrulama (`citations.py`):**
   - `split_sentences`: Türkçe kısaltmalar (`vb.`, `örn.`), ondalık sayılar ve tarihler korunarak cümle bölme; noktadan sonra gelen `[n]` atıflarını önceki cümleye bağlama.
   - 3 Deterministik Kontrol:
     1. `uncited_sentence`: Her cümlede en az bir `[n]` olmalıdır.
     2. `invalid_citation`: Atıf numarası blok aralığında (`1..len(blocks)`) olmalıdır.
     3. `number_not_in_source`: Cümledeki her rakam grubu (`\d+`), atıf yapılan kaynağın metninde veya başlığında bulunmalıdır.
   - `is_abstain`: Metin içinde `bulunamadı` geçiyorsa tutucu abstain kararı.

6. **RagAnswerService Orkestrasyonu (`service.py`):**
   - Kullanıcı sorusu gelir gelmez PII maskelenir; loglarda soru metni gizlenir.
   - Asenkron threadpool sınırı ile event loop bloklanmaz.
   - `no_results` ve `low_retrieval_score` durumlarında LLM çağrılmadan hızlı abstain.
   - En fazla 2 LLM denemesi; geçemezse `validation_failed` ile güvenli kurumsal abstain mesajı.

7. **Answer HTTP API (`app/api/answer.py`):**
   - `POST /rag/answer`: `question` (1..1000 karakter, boşluk korumalı), `k` (1..10), `source_file` filtresi.
   - Halka açık API yanıtında dahili teşhis alanları (`validation_issues`, `usage`, `top_dense_score`) sızdırılmaz.
   - RFC 7807 problem details ve 503 hata maskelemesi.

8. **Generation Değerlendirme Paketi (`app/rag/evaluation/generation/`):**
   - `eval/generation/answer_set.json`: 54 soru (42 cevaplanabilir golden set + 12 cevaplanamaz; 6 konu dışı + 6 tehlikeli yakın).
   - `dataset.py`: Doğrulayıcı ve yükleyici CLI (`--validate`).
   - `metrics.py`: Deterministik `fact_recall`, `forbidden_hit`, `correct`, `answer_accuracy`, `hallucination_rate`, `false_abstain_rate`, gecikme ve token metrikleri.
   - `gate.py`: Dense kosinüs skor dağılımı ölçümü ve eşik analizi.
   - `run.py`: Uçtan uca değerlendirme koşucusu; Markdown ve JSON raporlama.

---

### Doğrulama ve Test Özeti:
- **Toplam Birim Testi:** **324 test** (Tümü passed, 4 deselected, 0 failure).
- **Test Süresi:** ~36 saniye (`uv run pytest -m "not integration"`).
- **Ağ ve Docker Bağımsızlığı:** Tüm testler ağ bağlantısı veya Docker gerektirmeden bellek içi çalışır.

---

### Sıradaki Aşama (Next Step):
- **Aşama 5: Agent (tool calling, onaylı aksiyonlar, güvenlik paketi, agent eval)** — uygulanacak plan: `python_plan/agent.md` (Adım 0 → 10, sırayla).
  - **Adım 0-7 TAMAMLANDI:** Hazırlık, LLM Tool Round-Trip, Güvenlik Bağlamı (`RequestContext`), Downstream HTTP İstemcileri (`OrderClient`, `ShippingClient`), Tool Çatısı ve Okuma Araçları (`search_policy`, `get_order`, `list_my_orders`, `get_shipment`), Onaylı Aksiyonlar (`PendingActionStore`, `Kafka/LoggingTicketPublisher`, `ActionExecutor`), Prompt, Grounding & `AgentService` ReAct döngüsü, Agent HTTP API (`/agent/chat`, `/confirm`, `/reject`) ve `lifespan` entegrasyonu.
  - **Sırada:** **Adım 8 — Güvenlik Test Paketi (`tests/agent/test_security_suite.py`)** (IDOR, prompt injection, replay vb. 16 saldırgan senaryo).
  - **Ardından:** Adım 9 (Agent Evaluation) ve Adım 10 (Karar & Devir dokümantasyonu).
- Toplam test sayısı: **434 test** (Tümü passed, 0 failure).
