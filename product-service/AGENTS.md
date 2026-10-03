# Ürün Servisi (Product Service) - Geliştirme Yönergeleri (AGENTS.md)

> Bu belge, `product-service` için geçerli olan mimari kararları, yüksek okuma performansı (Cache-Aside) stratejisini ve veri modellerini tanımlar.

---

## 1. Servis Genel Bakışı
- **Dizin**: `product-service`
- **Paket**: `com.dgl.product`
- **Varsayılan Port**: `8081`
- **Veritabanı**: `product_db` (PostgreSQL - 5432) + Redis (6379)
- **Rolü**: Ürün kataloğu, kategoriler, fiyatlandırma ve yüksek performanslı önbellek yönetimi

Ürün servisi sistemin en yoğun okuma (read-heavy) trafiğine maruz kalan bileşenidir. Bu nedenle önbellekleme hayati önem taşır.

---

## 2. Önbellekleme Stratejisi (Redis Cache-Aside)

```text
              [GET /api/products/{id}]
                          │
                          ▼
                 Önbellek Kontrolü
                     (Redis)
                    /       \
             (Hit) /         \ (Miss)
                  ▼           ▼
             Redis Verisi    PostgreSQL DB
                              │
                              ▼
                         Redis'e Yaz (TTL)
```

1. **Cache-Aside Deseni**:
   - `GET /api/products/{id}` isteklerinde önce Redis kontrol edilir (`@Cacheable(value = "products", key = "#id")`).
   - Veri varsa doğrudan önbellekten mikrosaniyeler içinde dönülür.
   - Önbellekte yoksa PostgreSQL'den okunur, Redis'e TTL ile yazılır ve istemciye iletilir.
2. **Önbellek Geçersiz Kılma (Eviction)**:
   - Ürün güncellendiğinde veya silindiğinde `@CacheEvict(value = "products", key = "#id")` ile Redis'teki bayat veri derhal temizlenir.
3. **TTL (Time-To-Live)**:
   - Bayat veri riskini en aza indirmek için tüm önbellek kayıtları sıkı bir TTL (örneğin 30 dakika) ile tutulur.

---

## 3. REST API Uç Noktaları

- `GET /api/products` - Sayfalanmış ürün listesini döner.
- `GET /api/products/{id}` - Tekil ürün detayını getirir (Redis önbellekli).
- `GET /api/products/category/{categoryId}` - Kategoriye göre filtrelenmiş ürünleri listeler.
- `POST /api/products` - Yeni ürün tanımlar.
- `PUT /api/products/{id}` - Ürün bilgilerini ve fiyatını günceller (Önbelleği temizler).
- `DELETE /api/products/{id}` - Ürünü siler veya arşivler (Önbelleği temizler).

---

## 4. Paket Mimarisi

```text
com.dgl.product
├── config/              # RedisCacheConfig, DatabaseConfig
├── controller/          # ProductController, CategoryController
├── domain/              # Product, Category, Price, ProductStatus
├── dto/
│   ├── request/         # CreateProductRequest, UpdateProductRequest
│   └── response/        # ProductResponse, CategoryResponse
├── exception/           # ProductNotFoundException, SkuAlreadyExistsException
├── outbox/              # OutboxEvent, OutboxRepository, OutboxPublisher
├── repository/           # ProductRepository, CategoryRepository
└── service/             # ProductService, CategoryService
```

---

## 5. Derleme ve Test Komutları

```powershell
cd product-service
.\mvnw clean compile
.\mvnw test
.\mvnw spring-boot:run
cd ..
```
