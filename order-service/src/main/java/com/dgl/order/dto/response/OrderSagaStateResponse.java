package com.dgl.order.dto.response;

import java.time.Instant;

public record OrderSagaStateResponse(
    String currentStep,
    Instant inventoryReservedAt,
    Instant paymentAuthorizedAt,
    Instant shippingCreatedAt,
    String failureStep,
    String failureReason
) {}
