# Agent Mimari Karar Günlüğü (agent-decisions.md)

Bu belge, `ai-assistant-service` müşteri destek ajanı geliştirilirken alınan mimari kararları, kısıtları, güvenlik savunmalarını ve harici Java servisleri için devir notlarını belgeler.

---

## 1. Mimari Kararlar Özeti (Karar 1 - 15)

- **Karar 1 (Kimlik İzolasyonu)**: Müşteri kimliği asla modelden veya fonksiyon argümanlarından gelmez; doğrudan API Gateway tarafından doğrulanan `X-User-Id` HTTP başlığından (`RequestContext`) alınır ve downstream servislere taşınır.
- **Karar 2 (Kargo Sahiplik Doğrulaması)**: Kargo sorguları doğrudan kargo takip numarası (`track/{trackingNumber}`) ile yapılamaz; önce sipariş sahipliği `order-service` üzerinden doğrulanır, ardından sipariş ID ile kargo servisi çağrılır.
- **Karar 3 (Onaylı Aksiyonlar)**: Model doğrudan veritabanı veya sipariş iptali işlemi yapamaz; yalnızca müşteriye onaylatılmak üzere `PendingAction` önerisi oluşturabilir.
- **Karar 4 (Politika İzolasyonu ve Terminal RAG)**: Şirket kuralı / politika sorularında `search_policy` çağrılır ve `RagAnswerService` cevabı modele yeniden yazdırılmadan aynen döndürülür. Karma niyet desteklenmez.
- **Karar 5 (Kafka Outbox Sapması)**: `ai-assistant-service` ilişkisel bir veritabanına sahip olmadığı için Transactional Outbox deseni uygulanamaz. Destek talepleri doğrudan `aiokafka` ile yayınlanır (`at-least-once`).
- **Karar 6 (Sohbet Geçmişi Kapsam Dışı)**: Bu planda multi-turn geçmiş tutulmaz; her soru bağımsız olarak işlenir.
- **Karar 7 (LLM Tool Round-Trip Sözleşmesi)**: OpenAI, Claude ve Gemini için araç geri besleme sözleşmesi uygulandı. OpenAI/Local: role=assistant (tool_calls) ve role=tool (tool_call_id); Claude: assistant tool_use blokları ve ardışık tool_result bloklarının tek user mesajında birleştirilmesi (Anthropic Messages API kuralı); Gemini: Part.from_function_call ve Part.from_function_response ile role=user Content altında part birleştirme. FakeLLMProvider betikli tool_calls yanıtlarıyla genişletildi.
- **Karar 8 (Güvenlik Bağlamı ve Gateway Secret)**: `X-User-Id` başlığından normalize UUID çıkaran `RequestContext` ve `get_request_context` eklendi (eksik/geçersiz kimlik `401`). `require_gateway_secret` `hmac.compare_digest` ile router seviyesinde uygulandı (`403`); genel testlerin etkilenmemesi için `tests/conftest.py` autouse fixture'ı ile güvenlik varsayılan olarak testlerde kapatıldı.
- **Karar 9 (Downstream Client'lar ve PII Hijyeni)**: `OrderClient` ve `ShippingClient` sınıfları yazıldı. `DownstreamClient` GET isteklerinde ağ hatasında 1 kez tekrar denerken, POST (iptal) işlemlerinde kesinlikle retry yapmaz. `X-Gateway-Secret` ve `X-User-Id` iletilir; `X-User-Roles` admin bypass açığını önlemek için engellenir. `OrderView` ve `ShipmentView` modellerinde adres/alıcı PII alanları modele alınmayarak dış LLM sızıntısı önlendi. `order_number` için regex ile path injection koruması uygulandı.
- **Karar 10 (Tool Çatısı ve Okuma Tool'ları)**: `ToolContext`, `ToolResult`, `Tool` ve `ToolRegistry` yazıldı. Araç argüman modellerinde `extra="forbid"` ile modelden kimlik parametresi kabul edilmesi kesin olarak engellendi. `render_for_model` ile indirect prompt injection etiketleri (`<arac_sonucu>`) kaçırıldı ve 2000 karakter sınırı uygulandı. `SearchPolicyTool` RAG cevabını terminal olarak dönüştürür. `GetOrderTool` ve `ListMyOrdersTool` downstream yanıtında savunma derinliği olarak `customer_id == ctx.user_id` denetimi yapar. `GetShipmentTool` doğrudan takip no kabul etmez; önce sipariş sahipliğini doğrular, ardından sipariş ID ile kargo servisini sorgular. Hata durumlarında 404 ve 403 ayrımı yapılmadan 'Sipariş bulunamadı.' dönülerek ID tarama saldırıları engellendi.
- **Karar 11 (Onaylı Aksiyonlar, Pending Store ve Bilet Yayını)**: Yazma işlemleri modelin yetkisinden tamamen çıkarıldı. `RequestOrderCancellationTool` ve `RequestSupportTicketTool` doğrudan mikroservis çağırmaz veya olay yayınlamaz; yalnızca `PendingAction` oluşturur. `InMemoryPendingActionStore` `threading.Lock` ile korunur; atomik `consume` (pop) ile tek kullanımlık replay koruması sağlar, uyuşmayan kullanıcı denemesinde kaydı yakmaz ve 300 sn TTL ile süresi dolanları temizler. `ActionExecutor` onay anında sipariş durumunu yeniden sorgulayarak `CANCELLED` siparişlerde gereksiz POST yapmaz. Destek talepleri Unified Event Envelope standardında `LoggingTicketPublisher` veya Kafka ile yayınlanır.
- **Karar 12 (Sistem Prompt'u, Grounding ve AgentService Döngüsü)**: `AgentService` ReAct orkestrasyon döngüsü 4 adımla sınırlandırıldı. Kullanıcı sorusu girişte `mask_pii` ile maskelenir. `search_policy` çağrıldığında döngü terminal olarak sonlandırılır ve RAG cevabı atıflarıyla korunur. `check_reply_grounding` ile yanıttaki tüm rakam dizilerinin araç çıktılarında bulunması zorunlu kılındı; uydurma sayılarda 1 kez düzeltme hakkı tanınır, tekrarlanırsa güvenli fallback dönülür. Her konuşma turunda soru metni, tool argümanları ve ham kimlik sızdırmayan yapılandırılmış metrik logu (`user_id_hash` sha256 12 karakter) üretilir.
- **Karar 13 (Agent API & Yaşam Döngüsü Lifespan Bağlantısı)**: `POST /agent/chat`, `POST /agent/actions/{action_id}/confirm` ve `POST /agent/actions/{action_id}/reject` uç noktaları `require_gateway_secret` ve `get_request_context` ile korundu. `action_id` path parametresi regex ile doğrulanır (`^[A-Za-z0-9_\-]{16,64}$`). `confirm` ve `reject` yalnızca aksiyon sahibi `X-User-Id` tarafından bir defaya mahsus çalıştırılabilir (replay durumunda 404 döner). İstemci yanıtında dahili `usage`, `steps` veya araç logları sızdırılmaz. FastAPI `lifespan` üzerinden downstream client'lar, aksiyon deposu, ticket yayıncısı, araçlar ve agent servisi tekil olarak başlatılır; kapanışta açık asenkron bağlantılar düzgünce temizlenir.
- **Karar 14 (Güvenlik Test Paketi Doğrulaması - 16/16)**: `tests/agent/test_security_suite.py` altında 16 adet saldırgan (adversarial) senaryo kurgulandı ve tamamı ağsız `FakeLLMProvider` ve sahte taşımalarla yeşil olarak doğrulandı (güvenlik test paketi: 16/16). IDOR sızıntıları (tekil sipariş, sipariş listesi, kargo takibi), prompt injection (kullanıcı mesajı ve tool çıktısındaki etiket kaçırma), onaysız işlem engelleme, aksiyon çalma, tekrar oynatma (replay), TTL süre aşımı, durum değişimi yarış koşulu, path traversal / URL injection, politika aracında kimlik izolasyonu, log hijyeni (ham ID, metin ve tutar sızdırmama) ve gateway secret zorunluluğu uçtan uca kanıtlandı.
- **Karar 15 (Agent Değerlendirme Çerçevesi ve Deterministik Metrikler)**: `eval/agent/cases.json` altında 9 kategoride 39 vaka tanımlandı (elle yazılmış senaryolar). `dataset.py` ile tekil ID, geçerli tip ve adversarial güvenlik kısıtları doğrulandı (`--validate`). `scenarios.py` ile 3 müşterili izole mikroservis mock ortamı kuruldu. `metrics.py` ile LLM-judge kullanılmadan araç doğruluğu, tip doğruluğu, argüman doğruluğu ve kritik güvenlik metrikleri (`forbidden_call_rate`, `leak_rate`, `unconfirmed_write_rate`) hesaplandı. `run.py` CLI koşucusuna `--llm [fake|default]` ve `--embedder [fake|default]` bayrakları eklendi.
  - **Smoke Test vs. Güvenlik İddiası Netleştirmesi**: `--llm fake` smoke koşusu yalnızca değerlendirme işlem hattının, mock mikroservis taşımalarının ve metrik hesaplama motorunun hatasız çalıştığını kanıtlar; buradaki oranlar model yeteneğinin nihai kanıtı değildir. Sistemin asıl güvenlik kanıtı, modelin saldırgan hamlelerini deterministik olarak simüle eden ve tamamı yeşil geçen **16 senaryoluk `tests/agent/test_security_suite.py` güvenlik test paketidir** (Karar 14).
  - **Gerçek LLM Eval Notu**: Canlı model (`--llm default`) ile uçtan uca eval koşusu, ortamda `GEMINI_API_KEY` veya `OPENAI_API_KEY` tanımlandığında bağımsız olarak çalıştırılabilir; ağsız CI/CD ortamında ise deterministik smoke koşusu ve birim testler (`tests/agent/test_eval.py`) referans alınır.

---

## 2. Ajan Araçları (Tool Catalog) ve Varlık Nedenleri

| Araç Adı | Rolü ve Varlık Nedeni | Güvenlik / Kimlik İlkesi |
|---|---|---|
| `get_order` | Müşterinin tekil sipariş detayını, durumunu ve kalemlerini getirir. | Kimlik modelden alınmaz; `ToolContext.user_id` üzerinden downstream çağrılır. `extra="forbid"` ile ekstra kimlik argümanları reddedilir. `customer_id != user_id` durumunda `Sipariş bulunamadı.` döner. |
| `list_my_orders` | Müşterinin mevcut tüm siparişlerini listeler. | Yalnızca `ctx.user_id` siparişleri listelenir; dönen yanıtta başka müşterinin kaydı sızarsa savunma derinliği filtresiyle ayıklanır. |
| `get_shipment` | Siparişe bağlı kargo hareket ve takip detayını sorgular. | Asla doğrudan takip numarası almaz. Önce `order-service`'ten sipariş sahipliğini doğrular, ardından kargo servisine sipariş kimliği (`orderId`) ile gider. |
| `search_policy` | İade, garanti, teslimat, cayma hakkı gibi kurumsal politikaları yanıtlar. | Terminal RAG aracıdır. Kullanıcının maskelenmiş sorusu iletilir, kimlik sızdırılmaz. Yanıt modele özetletilmeden atıflarıyla birlikte birebir döner. |
| `request_order_cancellation` | Sipariş iptali için onaylı bekleyen aksiyon (`PendingAction`) üretir. | Asla doğrudan veritabanında iptal yapmaz. Sahipliği doğrular, 300 sn TTL ile depoya yazar. Müşteri onaylamadan işlem gerçekleşmez. |
| `request_support_ticket` | Yetkili görüşmesi ve şikayetler için destek bileti önerisi oluşturur. | Onaylı işlem önerisi üretir. Onaylandığında Kafka veya audit loguna `support.ticket.created` domain olayı basar. |

---

## 3. Java Mikroservisleri İçin Güvenlik ve Mimari Devir Notları (ÖNEMLİ)

Aşağıdaki iki açık, Java mikroservislerinde tespit edilmiş olup `ai-assistant-service` tarafında savunma derinliği (defense-in-depth) ile maskelenmiştir. Ancak bu açıkların **Java mikroservislerinin kendi kod tabanlarında kapatılması ayrı bir iş olarak planlanmalıdır**:

1. **`shipping-service` Sahiplik Açığı (`ShipmentResponse` / `track/` Uç Noktası)**:
   - **Sorun**: `shipping-service`'in `ShipmentResponse` DTO modelinde `customerId` alanı yer almamaktadır. Ayrıca `GET /api/v1/shipments/track/{trackingNumber}` uç noktası kimlik doğrulaması olmaksızın herkese açıktır. Herhangi bir kullanıcı başka birinin takip numarasını bildiğinde kargo hareketlerini ve adresini görebilir.
   - **Ajan Tarafındaki Geçici Çözüm**: Asistan asla `track/{trackingNumber}` çağırmaz. Önce `order-service` üzerinden sipariş sahipliğini doğrular, ardından `GET /api/v1/shipments/order/{orderId}` çağrısı yapar.
   - **Java Tarafında Yapılması Gereken**: `Shipment` entity'sine `customerId` eklenmeli, `track` uç noktası `X-User-Id` başlığıyla sahiplik doğrulaması yapmalıdır.

2. **`order-service` Başlıksız İstek Açığı (`enforceOwnership`)**:
   - **Sorun**: `order-service` içindeki `enforceOwnership(order, userId, userRoles)` metodunda, `userId` başlığı `null` veya boş string ise sahiplik kontrolü atlanmakta ve sipariş doğrudan dönebilmektedir (`if (userId != null && !userId.isBlank())`).
   - **Ajan Tarafındaki Geçici Çözüm**: `DownstreamClient` her istekte kesinlikle `X-User-Id` gönderir. Ek olarak `GetOrderTool` ve `ListMyOrdersTool`, downstream'den gelen `order.customer_id` ile `ctx.user_id`'yi kendisi de karşılaştırır (çift kontrol).
   - **Java Tarafında Yapılması Gereken**: `order-service` gelen istekte `X-User-Id` yoksa işlemi `401 Unauthorized` veya `403 Forbidden` ile fail-fast reddetmelidir.

---

## 4. Onaylı Aksiyon Modeli ve Bellek İçi Depo Sınırları

- **TTL**: Tüm bekleyen aksiyonlar için varsayılan TTL **300 saniyedir** (`settings.AGENT_PENDING_TTL_SEC`). Süresi dolan aksiyonlar `consume` edildiğinde atomik olarak `None` döner (`404 Not Found`).
- **Atomik Pop (`consume`)**: Aksiyon depodan okunurken tek adımda silinir (`del self._actions[action_id]`). Böylece iki eşzamanlı istek aynı işlemi iki kez tetikleyemez (Replay saldırısı koruması).
- **Hatalı Kullanıcı Korunumu**: Başka bir kullanıcının `action_id` tahmin etme denemesinde kayıt depodan silinmez; asıl hak sahibi kullanıcının işlem hakkı korunur.
- **Bellek İçi Deponun Sınırı (Production Notu)**: Mevcut `InMemoryPendingActionStore` tek örnekli (single instance) çalışma için tasarlanmıştır ve servis yeniden başladığında bekleyen aksiyonlar kaybolur. Yatayda birden fazla pod/container çalıştırılacaksa `PendingActionStore` Protocol arayüzü `RedisPendingActionStore` ile değiştirilmelidir.

---

## 5. Sağlayıcı Araç Sözleşmeleri (Round-Trip Schemas)

| Sağlayıcı | Model Çağrı Formatı | Araç Sonucu Geri Besleme Formatı |
|---|---|---|
| **OpenAI / Local** | `role: "assistant", tool_calls: [...]` | `role: "tool", tool_call_id: "...", name: "...", content: "..."` |
| **Anthropic Claude** | `role: "assistant", content: [ToolUseBlock(...)]` | `role: "user", content: [ToolResultBlock(...)]` *(Anthropic Messages API kuralı: Ardışık tüm tool sonuçları TEK bir user mesajında birleştirilir)* |
| **Google Gemini** | `content.parts[0].function_call` | `Part.from_function_response(name=..., response={...})` tek bir `role="user"` Content part listesinde birleştirilir. |
