package com.dgl.payment.dto.response;

import com.dgl.payment.domain.RefundStatus;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.UUID;

public record PaymentRefundResponse(
    UUID id,
    BigDecimal amount,
    String refundReason,
    String refundReference,
    RefundStatus status,
    Instant createdAt
) {}
