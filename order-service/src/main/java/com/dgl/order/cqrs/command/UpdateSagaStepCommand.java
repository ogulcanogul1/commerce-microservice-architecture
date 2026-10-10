package com.dgl.order.cqrs.command;

import com.dgl.order.cqrs.Command;
import com.dgl.order.domain.OrderStatus;
import com.dgl.order.dto.response.OrderResponse;

import java.util.UUID;

/**
 * Command to advance an order's Saga step state.
 */
public record UpdateSagaStepCommand(
        UUID orderId,
        String step,
        OrderStatus status,
        String failureReason
) implements Command<OrderResponse> {
}
