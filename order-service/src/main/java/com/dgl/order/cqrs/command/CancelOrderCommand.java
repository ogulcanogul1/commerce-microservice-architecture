package com.dgl.order.cqrs.command;

import com.dgl.order.cqrs.Command;
import com.dgl.order.dto.request.CancelOrderRequest;
import com.dgl.order.dto.response.OrderResponse;

import java.util.UUID;

/**
 * Command to cancel an active order and trigger Saga compensating transactions.
 */
public record CancelOrderCommand(
        UUID orderId,
        CancelOrderRequest request
) implements Command<OrderResponse> {
}
