package com.dgl.order.cqrs.command;

import com.dgl.order.cqrs.Command;
import com.dgl.order.dto.request.CreateOrderRequest;
import com.dgl.order.dto.response.OrderResponse;

import java.util.UUID;

/**
 * Command to place a new order and trigger the initial Saga workflow.
 */
public record CreateOrderCommand(
        CreateOrderRequest request,
        UUID correlationId
) implements Command<OrderResponse> {
}
