# Bildirim Servisi (Notification Service) - Geliştirme Yönergeleri (AGENTS.md)

> Bu belge, `notification-service` için geçerli olan mimari kararları, olay dinleme stratejisini ve bildirim simülasyon kurallarını tanımlar.

---

## 1. Servis Genel Bakışı
- **Dizin**: `notification-service`
- **Paket**: `com.dgl.notification`
- **Varsayılan Port**: `8087`
- **Veritabanı**: `notification_db` (PostgreSQL - 5432)
- **Rolü**: Tamamen olay güdümlü (Event-Driven Consumer), E-posta/SMS/Push bildirim simülatörü ve bildirim geçmişi saklama

Bu servis harici REST API çağırmaz; yalnızca Kafka konularını dinleyerek müşterilere ilgili bildirimleri şablonlar aracılığıyla gönderir.

---

## 2. Temel İlkeler ve Dağıtık Sistem Desenleri

### 2.1. Kesin Idempotency (Spam Önleme)
- Müşterilere aynı e-postanın veya SMS'in iki kez gitmesi kabul edilemez bir kullanıcı deneyimidir.
- Gelen her Kafka olayı için `processed_notifications` tablosunda `(event_id, channel)` kontrolü yapılır.
- Zaten gönderilmiş bir bildirim tekrar geldiğinde işlem sessizce atlanır.

### 2.2. Bildirim Kanalları ve Şablon Motoru
- Kanallar: `EMAIL`, `SMS`, `PUSH`.
- Başlangıç aşamasında gerçek SMTP / SMS sağlayıcısı yerine simüle edilmiş konsol / log sağlayıcıları (`SimulatedEmailSender`, `SimulatedSmsSender`) kullanılır.
- Olay yükündeki veriler (müşteri adı, sipariş numarası, tutar, kargo takip linki vb.) dinamik şablonlarla birleştirilir.

---

## 3. Dinlenen Kafka Konuları (Consumed Topics)

| Dinlenen Konu | Gönderilen Bildirim Türü | İçerik Özeti |
| :--- | :--- | :--- |
| `orders.confirmed` | `EMAIL` + `SMS` | Sipariş onaylandı, hazırlık süreci başladı |
| `orders.cancelled` | `EMAIL` | Sipariş iptali ve iade bilgilendirmesi |
| `payments.failed` | `EMAIL` + `SMS` | Ödeme başarısız oldu, ödeme yönteminizi güncelleyin uyarısı |
| `shipments.created` | `EMAIL` + `SMS` | Siparişiniz kargoya verildi + Takip Numarası |
| `shipments.delivered` | `EMAIL` + `PUSH`| Siparişiniz teslim edildi |

---

## 4. Paket Mimarisi

```text
com.dgl.notification
├── config/              # KafkaConsumerConfig, DatabaseConfig
├── domain/              # Notification, NotificationType, NotificationStatus, Channel
├── dto/                 # NotificationLogResponse
├── messaging/
│   ├── event/           # Tüketilen olay DTO'ları
│   └── consumer/        # OrderEventsConsumer, PaymentEventsConsumer, ShippingEventsConsumer
├── repository/           # NotificationRepository, ProcessedNotificationRepository
└── service/             # NotificationService, EmailSender, SmsSender, TemplateEngine
```

---

## 5. Derleme ve Test Komutları

```powershell
cd notification-service
.\mvnw clean compile
.\mvnw test
.\mvnw spring-boot:run
cd ..
```
