package com.dgl.product.dto.request;

import com.dgl.product.domain.ProductStatus;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Positive;
import jakarta.validation.constraints.Size;

import java.math.BigDecimal;
import java.util.Map;
import java.util.UUID;

public record UpdateProductRequest(
    @NotBlank(message = "Product name is required")
    @Size(max = 255, message = "Product name cannot exceed 255 characters")
    String name,

    String description,

    @NotNull(message = "Category ID is required")
    UUID categoryId,

    @NotNull(message = "Base price is required")
    @Positive(message = "Base price must be greater than zero")
    BigDecimal basePrice,

    ProductStatus status,

    Map<String, String> attributes
) {}
