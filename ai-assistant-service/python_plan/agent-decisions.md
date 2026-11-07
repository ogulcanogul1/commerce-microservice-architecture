# Agent Mimari Karar Günlüğü (agent-decisions.md)

Bu belge, `ai-assistant-service` müşteri destek ajanı geliştirilirken alınan mimari kararları, kısıtları ve gerekçelerini belgeler.

- **Başlangıç Durumu**: 332 test yeşil (PII telefon deseni düzeltildi). Generation eval kalite sayıları gerçek LLM ile henüz ölçülmedi.
- **Karar 1 (Kimlik İzolasyonu)**: Müşteri kimliği asla modelden veya parametrelerden gelmez; doğrudan `X-User-Id` HTTP başlığından alınır ve downstream'e taşınır.
- **Karar 2 (Kargo Sahiplik Doğrulaması)**: Kargo sorguları doğrudan kargo takip numarası ile yapılamaz; önce sipariş sahipliği `order-service` üzerinden doğrulanır.
- **Karar 3 (Onaylı Aksiyonlar)**: Model doğrudan veritabanı veya sipariş iptali işlemi yapamaz; yalnızca müşteriye onaylatılmak üzere `PendingAction` önerisi oluşturabilir.
- **Karar 4 (Politika İzolasyonu ve Terminal RAG)**: Şirket kuralı / politika sorularında `search_policy` çağrılır ve `RagAnswerService` cevabı modele yeniden yazdırılmadan aynen döndürülür. Karma niyet desteklenmez.
- **Karar 5 (Kafka Outbox Sapması)**: `ai-assistant-service` ilişkisel bir veritabanına sahip olmadığı için Transactional Outbox deseni uygulanamaz. Destek talepleri doğrudan `aiokafka` ile yayınlanır (`at-least-once`).
- **Karar 6 (Sohbet Geçmişi Kapsam Dışı)**: Bu planda multi-turn geçmiş tutulmaz; her soru bağımsız olarak işlenir.
- **Karar 7 (LLM Tool Round-Trip Sözleşmesi)**: OpenAI, Claude ve Gemini için araç geri besleme sözleşmesi uygulandı. OpenAI/Local: role=assistant (tool_calls) ve role=tool (tool_call_id); Claude: assistant tool_use blokları ve ardışık tool_result bloklarının tek user mesajında birleştirilmesi (Anthropic Messages API kuralı); Gemini: Part.from_function_call ve Part.from_function_response ile role=user Content altında part birleştirme. FakeLLMProvider betikli tool_calls yanıtlarıyla genişletildi.
