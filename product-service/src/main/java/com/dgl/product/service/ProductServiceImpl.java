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
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.stereotype.Service;

import java.util.UUID;

@Slf4j
@Service
@RequiredArgsConstructor
public class ProductServiceImpl implements ProductService {

    private final CommandBus commandBus;
    private final QueryBus queryBus;

    @Override
    public ProductResponse createProduct(CreateProductRequest request) {
        return commandBus.execute(new CreateProductCommand(request));
    }

    @Override
    public ProductResponse updateProduct(UUID id, UpdateProductRequest request) {
        return commandBus.execute(new UpdateProductCommand(id, request));
    }

    @Override
    public ProductResponse getProductById(UUID id) {
        return queryBus.execute(new GetProductByIdQuery(id));
    }

    @Override
    public ProductResponse getProductBySku(String sku) {
        return queryBus.execute(new GetProductBySkuQuery(sku));
    }

    @Override
    public ProductResponse getProductBySlug(String slug) {
        return queryBus.execute(new GetProductBySlugQuery(slug));
    }

    @Override
    public Page<ProductResponse> getAllProducts(Pageable pageable) {
        return queryBus.execute(new GetAllProductsQuery(pageable));
    }

    @Override
    public Page<ProductResponse> getProductsByCategory(UUID categoryId, Pageable pageable) {
        return queryBus.execute(new GetProductsByCategoryQuery(categoryId, pageable));
    }

    @Override
    public void deleteProduct(UUID id) {
        commandBus.execute(new DeleteProductCommand(id));
    }
}
