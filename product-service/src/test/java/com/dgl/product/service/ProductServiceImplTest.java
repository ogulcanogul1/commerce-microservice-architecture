package com.dgl.product.service;

import com.dgl.product.cqrs.CommandBus;
import com.dgl.product.cqrs.QueryBus;
import com.dgl.product.cqrs.command.CreateProductCommand;
import com.dgl.product.cqrs.command.DeleteProductCommand;
import com.dgl.product.cqrs.command.UpdateProductCommand;
import com.dgl.product.cqrs.query.*;
import com.dgl.product.dto.request.CreateProductRequest;
import com.dgl.product.dto.request.UpdateProductRequest;
import com.dgl.product.dto.response.ProductResponse;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageImpl;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;

import java.math.BigDecimal;
import java.util.List;
import java.util.Map;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.*;

@ExtendWith(MockitoExtension.class)
class ProductServiceImplTest {

    @Mock
    private CommandBus commandBus;

    @Mock
    private QueryBus queryBus;

    @InjectMocks
    private ProductServiceImpl productService;

    @Test
    @DisplayName("createProduct: Should dispatch CreateProductCommand")
    void createProduct_shouldDispatch() {
        CreateProductRequest request = new CreateProductRequest("SKU-1", "Prod", "Desc", UUID.randomUUID(), BigDecimal.TEN, "TRY", Map.of());
        ProductResponse expected = mock(ProductResponse.class);

        when(commandBus.execute(any(CreateProductCommand.class))).thenReturn(expected);

        ProductResponse actual = productService.createProduct(request);

        assertThat(actual).isSameAs(expected);
        verify(commandBus).execute(new CreateProductCommand(request));
    }

    @Test
    @DisplayName("updateProduct: Should dispatch UpdateProductCommand")
    void updateProduct_shouldDispatch() {
        UUID id = UUID.randomUUID();
        UpdateProductRequest request = new UpdateProductRequest("Name", "Desc", UUID.randomUUID(), BigDecimal.TEN, null, null);
        ProductResponse expected = mock(ProductResponse.class);

        when(commandBus.execute(any(UpdateProductCommand.class))).thenReturn(expected);

        ProductResponse actual = productService.updateProduct(id, request);

        assertThat(actual).isSameAs(expected);
        verify(commandBus).execute(new UpdateProductCommand(id, request));
    }

    @Test
    @DisplayName("getProductById: Should dispatch GetProductByIdQuery")
    void getProductById_shouldDispatch() {
        UUID id = UUID.randomUUID();
        ProductResponse expected = mock(ProductResponse.class);

        when(queryBus.execute(any(GetProductByIdQuery.class))).thenReturn(expected);

        ProductResponse actual = productService.getProductById(id);

        assertThat(actual).isSameAs(expected);
        verify(queryBus).execute(new GetProductByIdQuery(id));
    }

    @Test
    @DisplayName("getProductBySku: Should dispatch GetProductBySkuQuery")
    void getProductBySku_shouldDispatch() {
        ProductResponse expected = mock(ProductResponse.class);

        when(queryBus.execute(any(GetProductBySkuQuery.class))).thenReturn(expected);

        ProductResponse actual = productService.getProductBySku("SKU-1");

        assertThat(actual).isSameAs(expected);
        verify(queryBus).execute(new GetProductBySkuQuery("SKU-1"));
    }

    @Test
    @DisplayName("getProductBySlug: Should dispatch GetProductBySlugQuery")
    void getProductBySlug_shouldDispatch() {
        ProductResponse expected = mock(ProductResponse.class);

        when(queryBus.execute(any(GetProductBySlugQuery.class))).thenReturn(expected);

        ProductResponse actual = productService.getProductBySlug("slug-1");

        assertThat(actual).isSameAs(expected);
        verify(queryBus).execute(new GetProductBySlugQuery("slug-1"));
    }

    @Test
    @DisplayName("getAllProducts: Should dispatch GetAllProductsQuery")
    void getAllProducts_shouldDispatch() {
        Pageable pageable = PageRequest.of(0, 10);
        Page<ProductResponse> expected = new PageImpl<>(List.of());

        when(queryBus.execute(any(GetAllProductsQuery.class))).thenReturn(expected);

        Page<ProductResponse> actual = productService.getAllProducts(pageable);

        assertThat(actual).isSameAs(expected);
        verify(queryBus).execute(new GetAllProductsQuery(pageable));
    }

    @Test
    @DisplayName("getProductsByCategory: Should dispatch GetProductsByCategoryQuery")
    void getProductsByCategory_shouldDispatch() {
        UUID categoryId = UUID.randomUUID();
        Pageable pageable = PageRequest.of(0, 10);
        Page<ProductResponse> expected = new PageImpl<>(List.of());

        when(queryBus.execute(any(GetProductsByCategoryQuery.class))).thenReturn(expected);

        Page<ProductResponse> actual = productService.getProductsByCategory(categoryId, pageable);

        assertThat(actual).isSameAs(expected);
        verify(queryBus).execute(new GetProductsByCategoryQuery(categoryId, pageable));
    }

    @Test
    @DisplayName("deleteProduct: Should dispatch DeleteProductCommand")
    void deleteProduct_shouldDispatch() {
        UUID id = UUID.randomUUID();

        productService.deleteProduct(id);

        verify(commandBus).execute(new DeleteProductCommand(id));
    }
}
