package com.dgl.inventory.dto.request;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;

public record ReserveStockItem(
    @NotBlank(message = "SKU is required")
    String sku,

    @Min(value = 1, message = "Quantity must be at least 1")
    int quantity
) {}
