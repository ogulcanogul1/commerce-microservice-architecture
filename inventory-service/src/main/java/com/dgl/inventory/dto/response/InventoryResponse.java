package com.dgl.inventory.dto.response;

import java.time.Instant;
import java.util.UUID;

public record InventoryResponse(
    UUID id,
    String sku,
    int totalQuantity,
    int reservedQuantity,
    int availableQuantity,
    Instant createdAt,
    Instant updatedAt
) {}
