package com.dgl.product.messaging.event;

import java.math.BigDecimal;
import java.util.UUID;

public record ProductUpdatedPayload(
    UUID productId,
    String sku,
    String name,
    UUID categoryId,
    BigDecimal basePrice,
    String currency,
    String status
) {}
