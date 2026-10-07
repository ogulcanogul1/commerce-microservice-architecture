package com.dgl.order.dto.request;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Positive;

import java.math.BigDecimal;

public record CreateOrderItemRequest(
    @NotBlank(message = "SKU is required")
    String sku,

    @NotBlank(message = "Product name is required")
    String productName,

    @NotNull(message = "Unit price is required")
    @Positive(message = "Unit price must be positive")
    BigDecimal unitPrice,

    @Min(value = 1, message = "Quantity must be at least 1")
    int quantity
) {}
