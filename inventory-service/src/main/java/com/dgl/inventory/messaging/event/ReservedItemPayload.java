package com.dgl.inventory.messaging.event;

public record ReservedItemPayload(
    String sku,
    int quantity
) {}
