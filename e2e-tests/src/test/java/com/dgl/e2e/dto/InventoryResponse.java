package com.dgl.e2e.dto;

import java.util.UUID;

public record InventoryResponse(
        UUID id,
        String sku,
        int totalQuantity,
        int reservedQuantity,
        int availableQuantity
) {}
