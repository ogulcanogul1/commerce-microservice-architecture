package com.dgl.product.controller;

import com.dgl.product.cqrs.CommandBus;
import com.dgl.product.cqrs.QueryBus;
import com.dgl.product.cqrs.command.CreateProductCommand;
import com.dgl.product.cqrs.command.DeleteProductCommand;
import com.dgl.product.cqrs.command.UpdateProductCommand;
import com.dgl.product.cqrs.query.*;
import com.dgl.product.dto.request.CreateProductRequest;
import com.dgl.product.dto.request.UpdateProductRequest;
import com.dgl.product.dto.response.ProductResponse;
import org.junit.jupiter.api.BeforeEach;
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
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;

import java.math.BigDecimal;
import java.util.List;
import java.util.Map;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.*;

@ExtendWith(MockitoExtension.class)
class ProductControllerTest {

    @Mock
    private CommandBus commandBus;

    @Mock
    private QueryBus queryBus;

    @InjectMocks
    private ProductController controller;

    private UUID productId;
    private ProductResponse mockResponse;

    @BeforeEach
    void setUp() {
        productId = UUID.randomUUID();
        mockResponse = mock(ProductResponse.class);
    }

    @Test
    @DisplayName("CreateProduct: Should dispatch command and return 201")
    void createProduct_shouldReturn201() {
        CreateProductRequest request = new CreateProductRequest("SKU-1", "Prod", "Desc", UUID.randomUUID(), BigDecimal.TEN, "TRY", Map.of());
        when(commandBus.execute(any(CreateProductCommand.class))).thenReturn(mockResponse);

        ResponseEntity<ProductResponse> response = controller.createProduct(request);

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.CREATED);
        assertThat(response.getBody()).isSameAs(mockResponse);
        verify(commandBus).execute(new CreateProductCommand(request));
    }

    @Test
    @DisplayName("GetProductById: Should dispatch query and return 200")
    void getProductById_shouldReturn200() {
        when(queryBus.execute(any(GetProductByIdQuery.class))).thenReturn(mockResponse);

        ResponseEntity<ProductResponse> response = controller.getProductById(productId);

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.OK);
        verify(queryBus).execute(new GetProductByIdQuery(productId));
    }

    @Test
    @DisplayName("GetProductBySku: Should dispatch query and return 200")
    void getProductBySku_shouldReturn200() {
        when(queryBus.execute(any(GetProductBySkuQuery.class))).thenReturn(mockResponse);

        ResponseEntity<ProductResponse> response = controller.getProductBySku("SKU-1");

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.OK);
        verify(queryBus).execute(new GetProductBySkuQuery("SKU-1"));
    }

    @Test
    @DisplayName("GetProductBySlug: Should dispatch query and return 200")
    void getProductBySlug_shouldReturn200() {
        when(queryBus.execute(any(GetProductBySlugQuery.class))).thenReturn(mockResponse);

        ResponseEntity<ProductResponse> response = controller.getProductBySlug("slug-1");

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.OK);
        verify(queryBus).execute(new GetProductBySlugQuery("slug-1"));
    }

    @Test
    @DisplayName("GetAllProducts: Should dispatch query and return 200")
    void getAllProducts_shouldReturn200() {
        Pageable pageable = PageRequest.of(0, 10);
        Page<ProductResponse> page = new PageImpl<>(List.of(mockResponse));
        when(queryBus.execute(any(GetAllProductsQuery.class))).thenReturn(page);

        ResponseEntity<Page<ProductResponse>> response = controller.getAllProducts(pageable);

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.OK);
        verify(queryBus).execute(new GetAllProductsQuery(pageable));
    }

    @Test
    @DisplayName("UpdateProduct: Should dispatch command and return 200")
    void updateProduct_shouldReturn200() {
        UpdateProductRequest request = new UpdateProductRequest("Name", "Desc", UUID.randomUUID(), BigDecimal.TEN, null, null);
        when(commandBus.execute(any(UpdateProductCommand.class))).thenReturn(mockResponse);

        ResponseEntity<ProductResponse> response = controller.updateProduct(productId, request);

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.OK);
        verify(commandBus).execute(new UpdateProductCommand(productId, request));
    }

    @Test
    @DisplayName("DeleteProduct: Should dispatch command")
    void deleteProduct_shouldDispatch() {
        controller.deleteProduct(productId);
        verify(commandBus).execute(new DeleteProductCommand(productId));
    }
}
