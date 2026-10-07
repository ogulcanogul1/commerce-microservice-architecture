package com.dgl.shipping.messaging.event;

import java.time.Instant;
import java.util.UUID;

public record ShipmentDeliveredPayload(
    UUID shipmentId,
    UUID orderId,
    String trackingNumber,
    Instant deliveredAt
) {}
