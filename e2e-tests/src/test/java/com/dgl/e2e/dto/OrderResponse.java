package com.dgl.e2e.dto;

import java.math.BigDecimal;
import java.util.List;
import java.util.UUID;

public record OrderResponse(
        UUID id,
        String orderNumber,
        UUID customerId,
        String status,
        BigDecimal totalAmount,
        String currency,
        String shippingAddress,
        String failureReason,
        UUID correlationId,
        List<OrderItemResponse> items
) {}
