package com.dgl.product.cqrs.handler.command;

import com.dgl.product.cqrs.command.CreateProductCommand;
import com.dgl.product.cqrs.command.DeleteProductCommand;
import com.dgl.product.cqrs.command.UpdateProductCommand;
import com.dgl.product.cqrs.mapper.ProductResponseMapper;
import com.dgl.product.domain.Category;
import com.dgl.product.domain.Product;
import com.dgl.product.domain.ProductStatus;
import com.dgl.product.dto.request.CreateProductRequest;
import com.dgl.product.dto.request.UpdateProductRequest;
import com.dgl.product.dto.response.ProductResponse;
import com.dgl.product.exception.CategoryNotFoundException;
import com.dgl.product.exception.ProductAlreadyExistsException;
import com.dgl.product.exception.ProductNotFoundException;
import com.dgl.product.outbox.OutboxService;
import com.dgl.product.repository.CategoryRepository;
import com.dgl.product.repository.ProductRepository;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.Map;
import java.util.Optional;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.*;

@ExtendWith(MockitoExtension.class)
class ProductCommandHandlerTest {

    @Mock
    private ProductRepository productRepository;

    @Mock
    private CategoryRepository categoryRepository;

    @Mock
    private OutboxService outboxService;

    private final ProductResponseMapper mapper = new ProductResponseMapper();

    private CreateProductCommandHandler createHandler;
    private UpdateProductCommandHandler updateHandler;
    private DeleteProductCommandHandler deleteHandler;

    private UUID categoryId;
    private Category sampleCategory;
    private UUID productId;
    private Product sampleProduct;

    @BeforeEach
    void setUp() {
        createHandler = new CreateProductCommandHandler(productRepository, categoryRepository, outboxService, mapper);
        updateHandler = new UpdateProductCommandHandler(productRepository, categoryRepository, outboxService, mapper);
        deleteHandler = new DeleteProductCommandHandler(productRepository, outboxService);

        categoryId = UUID.randomUUID();
        sampleCategory = Category.builder().id(categoryId).name("Electronics").slug("electronics").build();

        productId = UUID.randomUUID();
        sampleProduct = Product.builder()
                .id(productId)
                .sku("SKU-100")
                .name("Smartphone")
                .slug("smartphone")
                .description("Flagship phone")
                .category(sampleCategory)
                .basePrice(new BigDecimal("999.99"))
                .currency("TRY")
                .status(ProductStatus.ACTIVE)
                .attributes(new ArrayList<>())
                .build();
    }

    @Test
    @DisplayName("CreateProduct: Should create product and emit Outbox event")
    void createProduct_shouldSucceed() {
        CreateProductRequest request = new CreateProductRequest(
                "SKU-100", "Smartphone", "Flagship phone", categoryId,
                new BigDecimal("999.99"), "TRY", Map.of("Color", "Black")
        );

        when(productRepository.existsBySku("SKU-100")).thenReturn(false);
        when(categoryRepository.findById(categoryId)).thenReturn(Optional.of(sampleCategory));
        when(productRepository.existsBySlug("smartphone")).thenReturn(false);
        when(productRepository.save(any(Product.class))).thenReturn(sampleProduct);

        ProductResponse response = createHandler.handle(new CreateProductCommand(request));

        assertThat(response).isNotNull();
        assertThat(response.sku()).isEqualTo("SKU-100");
        verify(outboxService).recordEvent(eq("Product"), eq(productId.toString()), eq("ProductCreated"), any(), isNull(), any());
    }

    @Test
    @DisplayName("CreateProduct: Duplicate SKU should throw ProductAlreadyExistsException")
    void createProduct_duplicateSku_shouldThrowException() {
        CreateProductRequest request = new CreateProductRequest(
                "SKU-100", "Smartphone", "Desc", categoryId,
                new BigDecimal("999.99"), "TRY", null
        );

        when(productRepository.existsBySku("SKU-100")).thenReturn(true);

        assertThatThrownBy(() -> createHandler.handle(new CreateProductCommand(request)))
                .isInstanceOf(ProductAlreadyExistsException.class);
    }

    @Test
    @DisplayName("UpdateProduct: Should update fields and emit Outbox event")
    void updateProduct_shouldSucceed() {
        UpdateProductRequest request = new UpdateProductRequest(
                "Smartphone Pro", "Updated desc", categoryId,
                new BigDecimal("1099.99"), ProductStatus.ACTIVE, Map.of()
        );

        when(productRepository.findById(productId)).thenReturn(Optional.of(sampleProduct));
        when(categoryRepository.findById(categoryId)).thenReturn(Optional.of(sampleCategory));

        ProductResponse response = updateHandler.handle(new UpdateProductCommand(productId, request));

        assertThat(response).isNotNull();
        assertThat(sampleProduct.getName()).isEqualTo("Smartphone Pro");
        verify(outboxService).recordEvent(eq("Product"), eq(productId.toString()), eq("ProductUpdated"), any(), isNull(), any());
    }

    @Test
    @DisplayName("DeleteProduct: Should archive product and emit Outbox event")
    void deleteProduct_shouldArchive() {
        when(productRepository.findById(productId)).thenReturn(Optional.of(sampleProduct));

        deleteHandler.handle(new DeleteProductCommand(productId));

        assertThat(sampleProduct.getStatus()).isEqualTo(ProductStatus.ARCHIVED);
        verify(outboxService).recordEvent(eq("Product"), eq(productId.toString()), eq("ProductDeleted"), any(), isNull(), any());
    }
}
