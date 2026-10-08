package com.dgl.product.service;

import com.dgl.product.domain.Category;
import com.dgl.product.domain.Product;
import com.dgl.product.domain.ProductStatus;
import com.dgl.product.dto.request.CreateProductRequest;
import com.dgl.product.dto.request.UpdateProductRequest;
import com.dgl.product.dto.response.ProductResponse;
import com.dgl.product.exception.CategoryNotFoundException;
import com.dgl.product.exception.ProductAlreadyExistsException;
import com.dgl.product.exception.ProductNotFoundException;
import com.dgl.product.messaging.event.ProductCreatedPayload;
import com.dgl.product.messaging.event.ProductDeletedPayload;
import com.dgl.product.messaging.event.ProductUpdatedPayload;
import com.dgl.product.outbox.OutboxService;
import com.dgl.product.repository.CategoryRepository;
import com.dgl.product.repository.ProductRepository;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageImpl;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.*;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.*;

@ExtendWith(MockitoExtension.class)
class ProductServiceImplTest {

    @Mock
    private ProductRepository productRepository;

    @Mock
    private CategoryRepository categoryRepository;

    @Mock
    private OutboxService outboxService;

    @InjectMocks
    private ProductServiceImpl productService;

    private Category electronics;

    @BeforeEach
    void setUp() {
        electronics = Category.builder()
                .id(UUID.randomUUID())
                .name("Electronics")
                .slug("electronics")
                .description("Electronic gadgets")
                .build();
    }

    @Test
    @DisplayName("createProduct should successfully create product and record ProductCreated outbox event")
    void createProduct_WhenValid_ShouldSucceedAndRecordOutboxEvent() {
        UUID categoryId = electronics.getId();
        CreateProductRequest request = new CreateProductRequest(
                "SKU-100",
                "Wireless Headphones",
                "High quality wireless headphones",
                categoryId,
                new BigDecimal("99.99"),
                "TRY",
                Map.of("color", "black", "bluetooth", "5.3")
        );

        when(productRepository.existsBySku("SKU-100")).thenReturn(false);
        when(categoryRepository.findById(categoryId)).thenReturn(Optional.of(electronics));
        when(productRepository.existsBySlug("wireless-headphones")).thenReturn(false);

        when(productRepository.save(any(Product.class))).thenAnswer(invocation -> {
            Product p = invocation.getArgument(0);
            p.setId(UUID.randomUUID());
            p.setCreatedAt(Instant.now());
            p.setUpdatedAt(Instant.now());
            return p;
        });

        ProductResponse response = productService.createProduct(request);

        assertThat(response).isNotNull();
        assertThat(response.sku()).isEqualTo("SKU-100");
        assertThat(response.name()).isEqualTo("Wireless Headphones");
        assertThat(response.slug()).isEqualTo("wireless-headphones");
        assertThat(response.status()).isEqualTo(ProductStatus.ACTIVE);
        assertThat(response.attributes()).containsEntry("color", "black");

        verify(outboxService, times(1)).recordEvent(
                eq("Product"),
                anyString(),
                eq("ProductCreated"),
                any(UUID.class),
                isNull(),
                any(ProductCreatedPayload.class)
        );
    }

    @Test
    @DisplayName("createProduct should throw ProductAlreadyExistsException when SKU already exists")
    void createProduct_WhenSkuExists_ShouldThrowException() {
        CreateProductRequest request = new CreateProductRequest(
                "SKU-DUPLICATE",
                "Test Product",
                "Description",
                UUID.randomUUID(),
                new BigDecimal("50.00"),
                "TRY",
                Map.of()
        );

        when(productRepository.existsBySku("SKU-DUPLICATE")).thenReturn(true);

        assertThatThrownBy(() -> productService.createProduct(request))
                .isInstanceOf(ProductAlreadyExistsException.class)
                .hasMessageContaining("SKU-DUPLICATE");

        verifyNoInteractions(categoryRepository);
        verifyNoInteractions(outboxService);
    }

    @Test
    @DisplayName("createProduct should throw CategoryNotFoundException when category does not exist")
    void createProduct_WhenCategoryNotFound_ShouldThrowException() {
        UUID categoryId = UUID.randomUUID();
        CreateProductRequest request = new CreateProductRequest(
                "SKU-200",
                "Test Product",
                "Description",
                categoryId,
                new BigDecimal("50.00"),
                "TRY",
                Map.of()
        );

        when(productRepository.existsBySku("SKU-200")).thenReturn(false);
        when(categoryRepository.findById(categoryId)).thenReturn(Optional.empty());

        assertThatThrownBy(() -> productService.createProduct(request))
                .isInstanceOf(CategoryNotFoundException.class);

        verifyNoInteractions(outboxService);
    }

    @Test
    @DisplayName("updateProduct should update product fields and record ProductUpdated outbox event")
    void updateProduct_WhenValid_ShouldSucceed() {
        UUID productId = UUID.randomUUID();
        Product product = Product.builder()
                .id(productId)
                .sku("SKU-300")
                .name("Old Name")
                .slug("old-name")
                .category(electronics)
                .basePrice(new BigDecimal("100.00"))
                .currency("TRY")
                .status(ProductStatus.ACTIVE)
                .attributes(new ArrayList<>())
                .build();

        UpdateProductRequest updateRequest = new UpdateProductRequest(
                "New Name",
                "Updated Description",
                electronics.getId(),
                new BigDecimal("150.00"),
                ProductStatus.INACTIVE,
                Map.of("warranty", "24-months")
        );

        when(productRepository.findById(productId)).thenReturn(Optional.of(product));
        when(categoryRepository.findById(electronics.getId())).thenReturn(Optional.of(electronics));

        ProductResponse response = productService.updateProduct(productId, updateRequest);

        assertThat(response).isNotNull();
        assertThat(product.getName()).isEqualTo("New Name");
        assertThat(product.getBasePrice()).isEqualByComparingTo("150.00");
        assertThat(product.getStatus()).isEqualTo(ProductStatus.INACTIVE);

        verify(outboxService, times(1)).recordEvent(
                eq("Product"),
                eq(productId.toString()),
                eq("ProductUpdated"),
                any(UUID.class),
                isNull(),
                any(ProductUpdatedPayload.class)
        );
    }

    @Test
    @DisplayName("updateProduct should throw ProductNotFoundException when product does not exist")
    void updateProduct_WhenNotFound_ShouldThrowException() {
        UUID productId = UUID.randomUUID();
        UpdateProductRequest updateRequest = new UpdateProductRequest(
                "Name", "Desc", UUID.randomUUID(), BigDecimal.TEN, ProductStatus.ACTIVE, Map.of()
        );

        when(productRepository.findById(productId)).thenReturn(Optional.empty());

        assertThatThrownBy(() -> productService.updateProduct(productId, updateRequest))
                .isInstanceOf(ProductNotFoundException.class);
    }

    @Test
    @DisplayName("getProductById should return product response when product exists")
    void getProductById_WhenExists_ShouldReturnResponse() {
        UUID productId = UUID.randomUUID();
        Product product = Product.builder()
                .id(productId)
                .sku("SKU-400")
                .name("Sample Product")
                .slug("sample-product")
                .category(electronics)
                .basePrice(new BigDecimal("200.00"))
                .status(ProductStatus.ACTIVE)
                .attributes(new ArrayList<>())
                .build();

        when(productRepository.findById(productId)).thenReturn(Optional.of(product));

        ProductResponse response = productService.getProductById(productId);

        assertThat(response).isNotNull();
        assertThat(response.id()).isEqualTo(productId);
        assertThat(response.sku()).isEqualTo("SKU-400");
    }

    @Test
    @DisplayName("getProductBySku should return product response when SKU exists")
    void getProductBySku_WhenExists_ShouldReturnResponse() {
        Product product = Product.builder()
                .id(UUID.randomUUID())
                .sku("SKU-500")
                .name("Sample Product")
                .slug("sample-product")
                .category(electronics)
                .basePrice(BigDecimal.TEN)
                .status(ProductStatus.ACTIVE)
                .attributes(new ArrayList<>())
                .build();

        when(productRepository.findBySku("SKU-500")).thenReturn(Optional.of(product));

        ProductResponse response = productService.getProductBySku("SKU-500");

        assertThat(response).isNotNull();
        assertThat(response.sku()).isEqualTo("SKU-500");
    }

    @Test
    @DisplayName("getProductBySlug should return product response when slug exists")
    void getProductBySlug_WhenExists_ShouldReturnResponse() {
        Product product = Product.builder()
                .id(UUID.randomUUID())
                .sku("SKU-600")
                .name("Sample Product")
                .slug("sample-product-slug")
                .category(electronics)
                .basePrice(BigDecimal.TEN)
                .status(ProductStatus.ACTIVE)
                .attributes(new ArrayList<>())
                .build();

        when(productRepository.findBySlug("sample-product-slug")).thenReturn(Optional.of(product));

        ProductResponse response = productService.getProductBySlug("sample-product-slug");

        assertThat(response).isNotNull();
        assertThat(response.slug()).isEqualTo("sample-product-slug");
    }

    @Test
    @DisplayName("deleteProduct should archive product and record ProductDeleted outbox event")
    void deleteProduct_WhenValid_ShouldArchiveAndRecordOutboxEvent() {
        UUID productId = UUID.randomUUID();
        Product product = Product.builder()
                .id(productId)
                .sku("SKU-700")
                .name("Product To Delete")
                .status(ProductStatus.ACTIVE)
                .build();

        when(productRepository.findById(productId)).thenReturn(Optional.of(product));

        productService.deleteProduct(productId);

        assertThat(product.getStatus()).isEqualTo(ProductStatus.ARCHIVED);

        verify(outboxService, times(1)).recordEvent(
                eq("Product"),
                eq(productId.toString()),
                eq("ProductDeleted"),
                any(UUID.class),
                isNull(),
                any(ProductDeletedPayload.class)
        );
    }

    @Test
    @DisplayName("getAllProducts should return paged response")
    void getAllProducts_ShouldReturnPagedResponse() {
        Product product = Product.builder()
                .id(UUID.randomUUID())
                .sku("SKU-800")
                .name("Paged Product")
                .category(electronics)
                .basePrice(BigDecimal.ONE)
                .status(ProductStatus.ACTIVE)
                .attributes(new ArrayList<>())
                .build();

        Pageable pageable = PageRequest.of(0, 10);
        when(productRepository.findAll(pageable)).thenReturn(new PageImpl<>(List.of(product)));

        Page<ProductResponse> page = productService.getAllProducts(pageable);

        assertThat(page).isNotNull();
        assertThat(page.getTotalElements()).isEqualTo(1);
    }
}
