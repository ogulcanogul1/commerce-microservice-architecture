package com.dgl.order.dto.response;

import com.dgl.order.domain.OrderStatus;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;
import java.util.UUID;

public record OrderResponse(
    UUID id,
    String orderNumber,
    UUID customerId,
    OrderStatus status,
    BigDecimal totalAmount,
    String currency,
    String shippingAddress,
    String failureReason,
    UUID correlationId,
    List<OrderItemResponse> items,
    OrderSagaStateResponse sagaState,
    Instant createdAt,
    Instant updatedAt
) {}
