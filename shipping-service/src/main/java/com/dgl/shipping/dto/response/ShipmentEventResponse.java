package com.dgl.shipping.dto.response;

import com.dgl.shipping.domain.ShipmentStatus;

import java.time.Instant;
import java.util.UUID;

public record ShipmentEventResponse(
    UUID id,
    ShipmentStatus status,
    String description,
    String location,
    Instant createdAt
) {}
