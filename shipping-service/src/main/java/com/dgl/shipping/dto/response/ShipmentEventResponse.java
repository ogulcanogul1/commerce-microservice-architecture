package com.dgl.shipping.dto.response;

import java.time.Instant;
import java.util.UUID;

public record ShipmentEventResponse(
    UUID id,
    String status,
    String description,
    String location,
    Instant eventTime
) {}
