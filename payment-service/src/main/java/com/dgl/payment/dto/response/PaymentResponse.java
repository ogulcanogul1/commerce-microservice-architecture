package com.dgl.payment.dto.response;

import com.dgl.payment.domain.PaymentStatus;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;
import java.util.UUID;

public record PaymentResponse(
    UUID id,
    UUID orderId,
    UUID customerId,
    BigDecimal amount,
    String currency,
    PaymentStatus status,
    String paymentMethod,
    String transactionReference,
    String idempotencyKey,
    String failureReason,
    List<PaymentRefundResponse> refunds,
    Instant createdAt,
    Instant updatedAt
) {}
