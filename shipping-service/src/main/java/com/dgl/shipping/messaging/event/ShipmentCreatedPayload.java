package com.dgl.shipping.messaging.event;

import java.time.Instant;
import java.util.UUID;

public record ShipmentCreatedPayload(
    UUID shipmentId,
    UUID orderId,
    String trackingNumber,
    String carrier,
    String recipientName,
    String deliveryAddress,
    Instant estimatedDelivery
) {}
