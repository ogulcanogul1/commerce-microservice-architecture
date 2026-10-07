package com.dgl.inventory.dto.request;

import jakarta.validation.constraints.NotNull;

import java.util.UUID;

public record ReleaseStockRequest(
    @NotNull(message = "Order ID is required")
    UUID orderId
) {}
