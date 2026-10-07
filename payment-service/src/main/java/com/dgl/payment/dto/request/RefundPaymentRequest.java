package com.dgl.payment.dto.request;

import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Positive;

import java.math.BigDecimal;

public record RefundPaymentRequest(
    @NotNull(message = "Refund amount is required")
    @Positive(message = "Refund amount must be positive")
    BigDecimal amount,

    String reason
) {}
