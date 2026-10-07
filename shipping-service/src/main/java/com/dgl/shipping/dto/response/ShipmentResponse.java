package com.dgl.shipping.dto.response;

import com.dgl.shipping.domain.Carrier;
import com.dgl.shipping.domain.ShipmentStatus;

import java.time.Instant;
import java.util.List;
import java.util.UUID;

public record ShipmentResponse(
    UUID id,
    UUID orderId,
    String trackingNumber,
    Carrier carrier,
    ShipmentStatus status,
    String recipientName,
    String deliveryAddress,
    Instant estimatedDelivery,
    Instant actualDelivery,
    String failureReason,
    List<ShipmentEventResponse> events,
    Instant createdAt,
    Instant updatedAt
) {}
