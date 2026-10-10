package com.dgl.order.cqrs.query;

import com.dgl.order.cqrs.Query;
import com.dgl.order.dto.response.OrderResponse;

/**
 * Query to retrieve order details by unique order number (e.g. ORD-12345678).
 */
public record GetOrderByOrderNumberQuery(String orderNumber) implements Query<OrderResponse> {
}
