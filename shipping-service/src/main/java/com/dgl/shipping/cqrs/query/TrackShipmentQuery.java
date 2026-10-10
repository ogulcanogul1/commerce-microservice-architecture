package com.dgl.shipping.cqrs.query;

import com.dgl.shipping.cqrs.Query;
import com.dgl.shipping.dto.response.TrackingResponse;

public record TrackShipmentQuery(String trackingNumber) implements Query<TrackingResponse> {
}
