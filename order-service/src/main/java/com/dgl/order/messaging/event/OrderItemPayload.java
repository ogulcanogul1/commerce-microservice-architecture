package com.dgl.order.messaging.event;

import java.math.BigDecimal;

public record OrderItemPayload(
    String sku,
    String productName,
    BigDecimal unitPrice,
    int quantity
) {}
