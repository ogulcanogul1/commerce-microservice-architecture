package com.dgl.order.cqrs.command;

import com.dgl.order.cqrs.Command;
import com.dgl.order.domain.OrderStatus;
import com.dgl.order.dto.response.OrderResponse;

import java.util.UUID;

/**
 * Command to update an order's lifecycle status and reason.
 */
public record UpdateOrderStatusCommand(
        UUID orderId,
        OrderStatus status,
        String failureReason
) implements Command<OrderResponse> {
}
