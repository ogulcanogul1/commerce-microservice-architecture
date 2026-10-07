package com.dgl.payment.messaging.event;

import java.math.BigDecimal;
import java.util.UUID;

public record PaymentCapturedPayload(
    UUID paymentId,
    UUID orderId,
    BigDecimal amount,
    String transactionReference
) {}
