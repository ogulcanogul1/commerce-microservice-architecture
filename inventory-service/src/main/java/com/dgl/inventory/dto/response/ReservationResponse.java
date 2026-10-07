package com.dgl.inventory.dto.response;

import com.dgl.inventory.domain.ReservationStatus;

import java.time.Instant;
import java.util.UUID;

public record ReservationResponse(
    UUID id,
    UUID orderId,
    String sku,
    int quantity,
    ReservationStatus status,
    Instant expiresAt,
    Instant createdAt
) {}
