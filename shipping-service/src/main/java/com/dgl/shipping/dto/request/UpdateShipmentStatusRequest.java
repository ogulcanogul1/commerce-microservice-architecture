package com.dgl.shipping.dto.request;

import com.dgl.shipping.domain.ShipmentStatus;
import jakarta.validation.constraints.NotNull;

public record UpdateShipmentStatusRequest(
    @NotNull(message = "Status is required")
    ShipmentStatus status,

    String description,

    String location
) {}
