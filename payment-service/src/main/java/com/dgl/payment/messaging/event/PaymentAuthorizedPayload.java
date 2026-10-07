package com.dgl.payment.messaging.event;

import java.math.BigDecimal;
import java.util.UUID;

public record PaymentAuthorizedPayload(
    UUID paymentId,
    UUID orderId,
    UUID customerId,
    BigDecimal amount,
    String currency,
    String transactionReference
) {}
