package com.dgl.product.dto.request;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Positive;
import jakarta.validation.constraints.Size;

import java.math.BigDecimal;
import java.util.Map;
import java.util.UUID;

public record CreateProductRequest(
    @NotBlank(message = "SKU is required")
    @Size(max = 50, message = "SKU cannot exceed 50 characters")
    String sku,

    @NotBlank(message = "Product name is required")
    @Size(max = 255, message = "Product name cannot exceed 255 characters")
    String name,

    String description,

    @NotNull(message = "Category ID is required")
    UUID categoryId,

    @NotNull(message = "Base price is required")
    @Positive(message = "Base price must be greater than zero")
    BigDecimal basePrice,

    @Size(min = 3, max = 3, message = "Currency must be a 3-letter ISO code")
    String currency,

    Map<String, String> attributes
) {}
