package com.dgl.inventory.messaging.event;

import java.util.List;
import java.util.UUID;

public record InventoryReservedPayload(
    UUID orderId,
    List<ReservedItemPayload> items
) {}
