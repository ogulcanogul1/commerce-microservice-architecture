package com.dgl.order.cqrs.query;

import com.dgl.order.cqrs.Query;
import com.dgl.order.dto.response.OrderResponse;

import java.util.UUID;

/**
 * Query to retrieve order details by order UUID.
 */
public record GetOrderByIdQuery(UUID orderId) implements Query<OrderResponse> {
}
