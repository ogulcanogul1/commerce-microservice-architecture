package com.dgl.order.messaging.event;

import java.math.BigDecimal;
import java.util.List;
import java.util.UUID;

public record OrderCreatedPayload(
    UUID orderId,
    String orderNumber,
    UUID customerId,
    BigDecimal totalAmount,
    String currency,
    String shippingAddress,
    List<OrderItemPayload> items
) {}
