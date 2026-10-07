package com.dgl.inventory.dto.request;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public record AddStockRequest(
    @NotBlank(message = "SKU is required")
    @Size(max = 50, message = "SKU cannot exceed 50 characters")
    String sku,

    @Min(value = 1, message = "Quantity must be at least 1")
    int quantity
) {}
