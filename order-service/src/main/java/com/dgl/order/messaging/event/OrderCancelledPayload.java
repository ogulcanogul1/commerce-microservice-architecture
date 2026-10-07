package com.dgl.order.messaging.event;

import java.util.UUID;

public record OrderCancelledPayload(
    UUID orderId,
    String orderNumber,
    String reason
) {}
