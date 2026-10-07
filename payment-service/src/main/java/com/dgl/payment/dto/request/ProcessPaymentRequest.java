package com.dgl.payment.dto.request;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Positive;

import java.math.BigDecimal;
import java.util.UUID;

public record ProcessPaymentRequest(
    @NotNull(message = "Order ID is required")
    UUID orderId,

    @NotNull(message = "Customer ID is required")
    UUID customerId,

    @NotNull(message = "Amount is required")
    @Positive(message = "Amount must be greater than zero")
    BigDecimal amount,

    String currency,

    @NotBlank(message = "Payment method is required")
    String paymentMethod
) {}
