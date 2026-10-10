package com.dgl.shipping.cqrs.query;

import com.dgl.shipping.cqrs.Query;
import com.dgl.shipping.dto.response.ShipmentResponse;

import java.util.UUID;

public record GetShipmentByOrderIdQuery(UUID orderId) implements Query<ShipmentResponse> {
}
