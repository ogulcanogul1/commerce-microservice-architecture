package com.dgl.inventory.messaging.event;

import java.util.UUID;

public record InventoryReleasedPayload(
    UUID orderId,
    String reason
) {}
