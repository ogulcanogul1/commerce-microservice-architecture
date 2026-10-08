package com.dgl.product.outbox;

import com.dgl.product.domain.Category;
import com.dgl.product.domain.Product;
import com.dgl.product.domain.ProductStatus;
import com.dgl.product.dto.request.CreateProductRequest;
import com.dgl.product.dto.request.UpdateProductRequest;
import com.dgl.product.dto.response.ProductResponse;
import com.dgl.product.repository.CategoryRepository;
import com.dgl.product.repository.ProductRepository;
import com.dgl.product.service.ProductService;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.kafka.test.context.EmbeddedKafka;
import org.springframework.test.annotation.DirtiesContext;

import java.math.BigDecimal;
import java.util.List;
import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
@DirtiesContext
@EmbeddedKafka(
        partitions = 1,
        topics = {
                "products.created",
                "products.updated",
                "products.deleted"
        }
)
class ProductOutboxIntegrationTest {

    @Autowired
    private ProductService productService;

    @Autowired
    private CategoryRepository categoryRepository;

    @Autowired
    private ProductRepository productRepository;

    @Autowired
    private OutboxEventRepository outboxEventRepository;

    @Autowired
    private OutboxPoller outboxPoller;

    private Category savedCategory;

    @BeforeEach
    void setUp() {
        outboxEventRepository.deleteAll();
        productRepository.deleteAll();
        categoryRepository.deleteAll();

        Category category = Category.builder()
                .name("Books")
                .slug("books")
                .description("All kinds of books")
                .build();
        savedCategory = categoryRepository.save(category);
    }

    @Test
    @DisplayName("Transactional Outbox: createProduct should persist entity and PENDING outbox event, then poller should publish it to Kafka")
    void createProduct_ShouldPersistOutboxAndPollerShouldPublish() {
        CreateProductRequest request = new CreateProductRequest(
                "SKU-BK-01",
                "Clean Architecture",
                "Software craftsmanship handbook",
                savedCategory.getId(),
                new BigDecimal("120.00"),
                "TRY",
                Map.of("author", "Robert C. Martin")
        );

        ProductResponse response = productService.createProduct(request);

        assertThat(response).isNotNull();
        assertThat(productRepository.existsById(response.id())).isTrue();

        List<OutboxEvent> pendingEvents = outboxEventRepository.findAll();
        assertThat(pendingEvents).hasSize(1);

        OutboxEvent outboxEvent = pendingEvents.getFirst();
        assertThat(outboxEvent.getStatus()).isEqualTo(OutboxStatus.PENDING);
        assertThat(outboxEvent.getAggregateType()).isEqualTo("Product");
        assertThat(outboxEvent.getAggregateId()).isEqualTo(response.id().toString());
        assertThat(outboxEvent.getType()).isEqualTo("ProductCreated");
        assertThat(outboxEvent.getPayload()).contains("Clean Architecture");

        // Execute poller
        outboxPoller.pollAndPublish();

        // Verify status transitioned to PUBLISHED
        OutboxEvent publishedEvent = outboxEventRepository.findById(outboxEvent.getId()).orElseThrow();
        assertThat(publishedEvent.getStatus()).isEqualTo(OutboxStatus.PUBLISHED);
        assertThat(publishedEvent.getProcessedAt()).isNotNull();
    }

    @Test
    @DisplayName("Transactional Outbox: updateProduct and deleteProduct should persist corresponding outbox events")
    void updateAndDeleteProduct_ShouldPersistOutboxEvents() {
        CreateProductRequest createRequest = new CreateProductRequest(
                "SKU-BK-02",
                "Refactoring",
                "Martin Fowler",
                savedCategory.getId(),
                new BigDecimal("150.00"),
                "TRY",
                Map.of()
        );

        ProductResponse created = productService.createProduct(createRequest);
        outboxEventRepository.deleteAll(); // clear initial event

        // 1. Update product
        UpdateProductRequest updateRequest = new UpdateProductRequest(
                "Refactoring 2nd Edition",
                "Updated",
                savedCategory.getId(),
                new BigDecimal("180.00"),
                ProductStatus.ACTIVE,
                Map.of()
        );
        productService.updateProduct(created.id(), updateRequest);

        List<OutboxEvent> updateEvents = outboxEventRepository.findAll();
        assertThat(updateEvents).hasSize(1);
        assertThat(updateEvents.getFirst().getType()).isEqualTo("ProductUpdated");

        outboxPoller.pollAndPublish();
        assertThat(outboxEventRepository.findById(updateEvents.getFirst().getId()).orElseThrow().getStatus())
                .isEqualTo(OutboxStatus.PUBLISHED);

        // 2. Delete (archive) product
        productService.deleteProduct(created.id());

        List<OutboxEvent> allEvents = outboxEventRepository.findAll();
        OutboxEvent deleteEvent = allEvents.stream()
                .filter(e -> "ProductDeleted".equals(e.getType()))
                .findFirst()
                .orElseThrow();

        assertThat(deleteEvent.getStatus()).isEqualTo(OutboxStatus.PENDING);

        outboxPoller.pollAndPublish();
        assertThat(outboxEventRepository.findById(deleteEvent.getId()).orElseThrow().getStatus())
                .isEqualTo(OutboxStatus.PUBLISHED);

        Product archivedProduct = productRepository.findById(created.id()).orElseThrow();
        assertThat(archivedProduct.getStatus()).isEqualTo(ProductStatus.ARCHIVED);
    }
}
