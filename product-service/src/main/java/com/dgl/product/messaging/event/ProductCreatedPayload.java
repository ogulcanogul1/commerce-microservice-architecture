package com.dgl.product.messaging.event;

import java.math.BigDecimal;
import java.util.UUID;

public record ProductCreatedPayload(
    UUID productId,
    String sku,
    String name,
    String slug,
    UUID categoryId,
    BigDecimal basePrice,
    String currency,
    String status
) {}
