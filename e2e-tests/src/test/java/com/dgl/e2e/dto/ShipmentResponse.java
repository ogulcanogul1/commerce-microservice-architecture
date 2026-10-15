package com.dgl.e2e.dto;

import java.util.UUID;

public record ShipmentResponse(
        UUID id,
        UUID orderId,
        String trackingNumber,
        String carrier,
        String status,
        String recipientAddress
) {}
