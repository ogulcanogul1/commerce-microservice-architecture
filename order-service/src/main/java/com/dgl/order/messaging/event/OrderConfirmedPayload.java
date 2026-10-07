package com.dgl.order.messaging.event;

import java.math.BigDecimal;
import java.util.UUID;

public record OrderConfirmedPayload(
    UUID orderId,
    String orderNumber,
    UUID customerId,
    BigDecimal totalAmount
) {}
