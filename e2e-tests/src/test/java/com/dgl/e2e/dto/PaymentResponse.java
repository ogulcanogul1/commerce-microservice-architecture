package com.dgl.e2e.dto;

import java.math.BigDecimal;
import java.util.UUID;

public record PaymentResponse(
        UUID id,
        UUID orderId,
        UUID customerId,
        BigDecimal amount,
        String currency,
        String status,
        String paymentMethod,
        String idempotencyKey,
        String failureReason
) {}
