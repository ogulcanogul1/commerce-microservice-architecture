package com.dgl.product.cqrs.handler.query;

import com.dgl.product.cqrs.mapper.ProductResponseMapper;
import com.dgl.product.cqrs.query.*;
import com.dgl.product.domain.Product;
import com.dgl.product.domain.ProductStatus;
import com.dgl.product.dto.response.ProductResponse;
import com.dgl.product.exception.ProductNotFoundException;
import com.dgl.product.repository.CategoryRepository;
import com.dgl.product.repository.ProductRepository;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageImpl;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;

import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.List;
import java.util.Optional;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class ProductQueryHandlerTest {

    @Mock
    private ProductRepository productRepository;

    @Mock
    private CategoryRepository categoryRepository;

    private final ProductResponseMapper mapper = new ProductResponseMapper();

    private GetProductByIdQueryHandler getByIdHandler;
    private GetProductBySkuQueryHandler getBySkuHandler;
    private GetProductBySlugQueryHandler getBySlugHandler;
    private GetAllProductsQueryHandler getAllHandler;
    private GetProductsByCategoryQueryHandler getByCategoryHandler;

    private UUID productId;
    private Product sampleProduct;

    @BeforeEach
    void setUp() {
        getByIdHandler = new GetProductByIdQueryHandler(productRepository, mapper);
        getBySkuHandler = new GetProductBySkuQueryHandler(productRepository, mapper);
        getBySlugHandler = new GetProductBySlugQueryHandler(productRepository, mapper);
        getAllHandler = new GetAllProductsQueryHandler(productRepository, mapper);
        getByCategoryHandler = new GetProductsByCategoryQueryHandler(productRepository, categoryRepository, mapper);

        productId = UUID.randomUUID();
        sampleProduct = Product.builder()
                .id(productId)
                .sku("SKU-999")
                .name("Keyboard")
                .slug("keyboard")
                .basePrice(new BigDecimal("120.00"))
                .currency("TRY")
                .status(ProductStatus.ACTIVE)
                .attributes(new ArrayList<>())
                .build();
    }

    @Test
    @DisplayName("GetProductById: Should return product response")
    void getProductById_shouldSucceed() {
        when(productRepository.findById(productId)).thenReturn(Optional.of(sampleProduct));

        ProductResponse response = getByIdHandler.handle(new GetProductByIdQuery(productId));

        assertThat(response).isNotNull();
        assertThat(response.id()).isEqualTo(productId);
    }

    @Test
    @DisplayName("GetProductBySku: Should return product response")
    void getProductBySku_shouldSucceed() {
        when(productRepository.findBySku("SKU-999")).thenReturn(Optional.of(sampleProduct));

        ProductResponse response = getBySkuHandler.handle(new GetProductBySkuQuery("SKU-999"));

        assertThat(response).isNotNull();
        assertThat(response.sku()).isEqualTo("SKU-999");
    }

    @Test
    @DisplayName("GetProductBySlug: Should return product response")
    void getProductBySlug_shouldSucceed() {
        when(productRepository.findBySlug("keyboard")).thenReturn(Optional.of(sampleProduct));

        ProductResponse response = getBySlugHandler.handle(new GetProductBySlugQuery("keyboard"));

        assertThat(response).isNotNull();
        assertThat(response.slug()).isEqualTo("keyboard");
    }

    @Test
    @DisplayName("GetAllProducts: Should return paginated products")
    void getAllProducts_shouldSucceed() {
        Pageable pageable = PageRequest.of(0, 10);
        when(productRepository.findAll(pageable)).thenReturn(new PageImpl<>(List.of(sampleProduct)));

        Page<ProductResponse> response = getAllHandler.handle(new GetAllProductsQuery(pageable));

        assertThat(response.getContent()).hasSize(1);
    }
}
