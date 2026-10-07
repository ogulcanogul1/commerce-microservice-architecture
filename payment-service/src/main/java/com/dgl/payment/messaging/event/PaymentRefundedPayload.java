package com.dgl.payment.messaging.event;

import java.math.BigDecimal;
import java.util.UUID;

public record PaymentRefundedPayload(
    UUID paymentId,
    UUID orderId,
    BigDecimal refundAmount,
    String refundReference,
    String reason
) {}
