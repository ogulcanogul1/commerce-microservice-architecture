package com.dgl.inventory.dto.request;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;

import java.util.List;
import java.util.UUID;

public record ReserveStockRequest(
    @NotNull(message = "Order ID is required")
    UUID orderId,

    @NotEmpty(message = "Items list cannot be empty")
    @Valid
    List<ReserveStockItem> items,

    Long ttlMinutes
) {}
