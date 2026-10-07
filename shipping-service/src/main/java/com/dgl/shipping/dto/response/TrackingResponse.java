package com.dgl.shipping.dto.response;

import com.dgl.shipping.domain.Carrier;
import com.dgl.shipping.domain.ShipmentStatus;

import java.time.Instant;
import java.util.List;

public record TrackingResponse(
    String trackingNumber,
    Carrier carrier,
    ShipmentStatus currentStatus,
    Instant estimatedDelivery,
    Instant actualDelivery,
    List<ShipmentEventResponse> history
) {}
