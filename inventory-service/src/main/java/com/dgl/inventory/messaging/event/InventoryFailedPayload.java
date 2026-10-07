package com.dgl.inventory.messaging.event;

import java.util.UUID;

public record InventoryFailedPayload(
    UUID orderId,
    String sku,
    int requestedQuantity,
    int availableQuantity,
    String reason
) {}
