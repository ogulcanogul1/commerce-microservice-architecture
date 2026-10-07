package com.dgl.product.messaging.event;

import java.util.UUID;

public record ProductDeletedPayload(
    UUID productId,
    String sku
) {}
