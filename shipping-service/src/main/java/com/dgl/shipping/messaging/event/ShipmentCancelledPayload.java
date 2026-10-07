package com.dgl.shipping.messaging.event;

import java.util.UUID;

public record ShipmentCancelledPayload(
    UUID shipmentId,
    UUID orderId,
    String trackingNumber,
    String reason
) {}
