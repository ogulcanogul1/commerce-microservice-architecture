package com.dgl.order.service;

import com.dgl.order.cqrs.CommandBus;
import com.dgl.order.cqrs.QueryBus;
import com.dgl.order.cqrs.command.*;
import com.dgl.order.cqrs.query.GetOrderByOrderNumberQuery;
import com.dgl.order.cqrs.query.GetOrderByIdQuery;
import com.dgl.order.cqrs.query.GetOrdersByCustomerQuery;
import com.dgl.order.domain.OrderStatus;
import com.dgl.order.dto.request.CancelOrderRequest;
import com.dgl.order.dto.request.CreateOrderRequest;
import com.dgl.order.dto.response.OrderResponse;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.stereotype.Service;

import java.util.UUID;

@Slf4j
@Service
@RequiredArgsConstructor
public class OrderServiceImpl implements OrderService {

    private final CommandBus commandBus;
    private final QueryBus queryBus;

    @Override
    public OrderResponse createOrder(CreateOrderRequest request, UUID correlationId) {
        return commandBus.execute(new CreateOrderCommand(request, correlationId));
    }

    @Override
    public OrderResponse getOrderById(UUID id) {
        return queryBus.execute(new GetOrderByIdQuery(id));
    }

    @Override
    public OrderResponse getOrderByOrderNumber(String orderNumber) {
        return queryBus.execute(new GetOrderByOrderNumberQuery(orderNumber));
    }

    @Override
    public Page<OrderResponse> getOrdersByCustomer(UUID customerId, Pageable pageable) {
        return queryBus.execute(new GetOrdersByCustomerQuery(customerId, pageable));
    }

    @Override
    public OrderResponse cancelOrder(UUID id, CancelOrderRequest request) {
        return commandBus.execute(new CancelOrderCommand(id, request));
    }

    @Override
    public OrderResponse updateOrderStatus(UUID id, OrderStatus newStatus, String failureReason) {
        return commandBus.execute(new UpdateOrderStatusCommand(id, newStatus, failureReason));
    }

    @Override
    public OrderResponse updateSagaStep(UUID id, String step, OrderStatus status, String failureReason) {
        return commandBus.execute(new UpdateSagaStepCommand(id, step, status, failureReason));
    }

    @Override
    public void handleInventoryReserved(UUID orderId) {
        commandBus.execute(new HandleInventoryReservedCommand(orderId));
    }

    @Override
    public void handleInventoryFailed(UUID orderId, String reason) {
        commandBus.execute(new HandleInventoryFailedCommand(orderId, reason));
    }

    @Override
    public void handlePaymentAuthorized(UUID orderId) {
        commandBus.execute(new HandlePaymentAuthorizedCommand(orderId));
    }

    @Override
    public void handlePaymentFailed(UUID orderId, String reason) {
        commandBus.execute(new HandlePaymentFailedCommand(orderId, reason));
    }

    @Override
    public void handleShipmentCreated(UUID orderId) {
        commandBus.execute(new HandleShipmentCreatedCommand(orderId));
    }

    @Override
    public void handleSagaTimeout(UUID orderId) {
        commandBus.execute(new HandleSagaTimeoutCommand(orderId));
    }
}
