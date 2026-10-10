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
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.responses.ApiResponses;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.UUID;

@RestController
@RequestMapping({"/api/v1/products", "/api/products"})
@RequiredArgsConstructor
@Tag(name = "Products", description = "Endpoints for managing products, categories, SKU, and stock")
public class ProductController {

    private final CommandBus commandBus;
    private final QueryBus queryBus;

    @PostMapping
    @Operation(summary = "Create a new product", description = "Adds a product to the catalog with SKU, initial stock, and category")
    @ApiResponses({
            @ApiResponse(responseCode = "201", description = "Product created successfully"),
            @ApiResponse(responseCode = "400", description = "Validation error or invalid product data"),
            @ApiResponse(responseCode = "409", description = "Duplicate SKU or slug")
    })
    public ResponseEntity<ProductResponse> createProduct(@Valid @RequestBody CreateProductRequest request) {
        ProductResponse response = commandBus.execute(new CreateProductCommand(request));
        return ResponseEntity.status(HttpStatus.CREATED).body(response);
    }

    @GetMapping("/{id}")
    @Operation(summary = "Get product by ID", description = "Fetches a product from cache or database by its unique identifier")
    @ApiResponses({
            @ApiResponse(responseCode = "200", description = "Product found"),
            @ApiResponse(responseCode = "404", description = "Product not found")
    })
    public ResponseEntity<ProductResponse> getProductById(@PathVariable UUID id) {
        ProductResponse response = queryBus.execute(new GetProductByIdQuery(id));
        return ResponseEntity.ok(response);
    }

    @GetMapping("/sku/{sku}")
    @Operation(summary = "Get product by SKU", description = "Fetches a product using its unique Stock Keeping Unit (SKU)")
    @ApiResponses({
            @ApiResponse(responseCode = "200", description = "Product found"),
            @ApiResponse(responseCode = "404", description = "Product not found")
    })
    public ResponseEntity<ProductResponse> getProductBySku(@PathVariable String sku) {
        ProductResponse response = queryBus.execute(new GetProductBySkuQuery(sku));
        return ResponseEntity.ok(response);
    }

    @GetMapping("/slug/{slug}")
    @Operation(summary = "Get product by slug", description = "Fetches a product using its SEO-friendly URL slug")
    @ApiResponses({
            @ApiResponse(responseCode = "200", description = "Product found"),
            @ApiResponse(responseCode = "404", description = "Product not found")
    })
    public ResponseEntity<ProductResponse> getProductBySlug(@PathVariable String slug) {
        ProductResponse response = queryBus.execute(new GetProductBySlugQuery(slug));
        return ResponseEntity.ok(response);
    }

    @GetMapping
    @Operation(summary = "List all products", description = "Retrieves a paginated list of catalog products")
    public ResponseEntity<Page<ProductResponse>> getAllProducts(Pageable pageable) {
        Page<ProductResponse> response = queryBus.execute(new GetAllProductsQuery(pageable));
        return ResponseEntity.ok(response);
    }

    @GetMapping("/category/{categoryId}")
    @Operation(summary = "List products by category", description = "Retrieves a paginated list of products under a specific category")
    public ResponseEntity<Page<ProductResponse>> getProductsByCategory(
            @PathVariable UUID categoryId, Pageable pageable) {
        Page<ProductResponse> response = queryBus.execute(new GetProductsByCategoryQuery(categoryId, pageable));
        return ResponseEntity.ok(response);
    }

    @PutMapping("/{id}")
    @Operation(summary = "Update an existing product", description = "Updates product fields and evicts cached entries")
    @ApiResponses({
            @ApiResponse(responseCode = "200", description = "Product updated successfully"),
            @ApiResponse(responseCode = "404", description = "Product not found")
    })
    public ResponseEntity<ProductResponse> updateProduct(
            @PathVariable UUID id, @Valid @RequestBody UpdateProductRequest request) {
        ProductResponse response = commandBus.execute(new UpdateProductCommand(id, request));
        return ResponseEntity.ok(response);
    }

    @DeleteMapping("/{id}")
    @ResponseStatus(HttpStatus.NO_CONTENT)
    @Operation(summary = "Delete product", description = "Removes a product from the catalog and invalidates cache")
    @ApiResponses({
            @ApiResponse(responseCode = "204", description = "Product deleted"),
            @ApiResponse(responseCode = "404", description = "Product not found")
    })
    public void deleteProduct(@PathVariable UUID id) {
        commandBus.execute(new DeleteProductCommand(id));
    }
}
