# Müşteri Servisi (Customer Service) - Geliştirme Yönergeleri (AGENTS.md)

> Bu belge, `customer-service` için geçerli olan mimari kararları, müşteri veri modellerini ve kuralları tanımlar.

---

## 1. Servis Genel Bakışı
- **Dizin**: `customer-service`
- **Paket**: `com.dgl.customer`
- **Varsayılan Port**: `8086`
- **Veritabanı**: `customer_db` (PostgreSQL - 5432)
- **Rolü**: Müşteri profilleri, teslimat/fatura adresleri, kullanıcı tercihleri ve müşteri aktivite yönetimi

---

## 2. Temel Sorumluluklar ve Kurallar

1. **Veri Bütünlüğü ve Validasyon**:
   - E-posta adresleri tekil (unique) olmalıdır.
   - Telefon ve adres bilgileri Jakarta Bean Validation ile doğrulanmalıdır.
2. **Olay Yayını (Customer Events)**:
   - Müşteri profilinde veya teslimat adresinde kritik değişiklik olduğunda diğer servislerin (örneğin kargo veya sipariş) haberdar olabilmesi için `customers.updated` olayı Transactional Outbox üzerinden fırlatılır.

---

## 3. Kafka Konuları (Topics)

### Üretilen Olaylar (Produced):
- `customers.updated` - Müşteri iletişim veya adres bilgileri güncellendiğinde yayınlanır.

---

## 4. REST API Uç Noktaları

- `POST /api/customers` - Yeni müşteri hesabı oluşturur.
- `GET /api/customers/{id}` - Müşteri profil detayını döner.
- `PUT /api/customers/{id}` - Profil bilgilerini günceller.
- `POST /api/customers/{id}/addresses` - Yeni teslimat/fatura adresi ekler.
- `GET /api/customers/{id}/addresses` - Müşterinin kayıtlı adreslerini listeler.

---

## 5. Paket Mimarisi

```text
com.dgl.customer
├── config/              # DatabaseConfig, KafkaConfig
├── controller/          # CustomerController, AddressController
├── domain/              # Customer, Address, CustomerPreferences
├── dto/
│   ├── request/         # CreateCustomerRequest, UpdateAddressRequest
│   └── response/        # CustomerResponse, AddressResponse
├── exception/           # CustomerNotFoundException, EmailAlreadyExistsException
├── messaging/
│   ├── event/           # CustomerUpdatedPayload
│   └── producer/        # CustomerEventProducer
├── outbox/              # OutboxEvent, OutboxRepository, OutboxPublisher
├── repository/           # CustomerRepository, AddressRepository
└── service/             # CustomerService, AddressService
```

---

## 6. Derleme ve Test Komutları

```powershell
cd customer-service
.\mvnw clean compile
.\mvnw test
.\mvnw spring-boot:run
cd ..
```
