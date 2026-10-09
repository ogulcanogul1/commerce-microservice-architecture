package com.dgl.order.service;

import com.dgl.order.domain.OrderStatus;
import com.dgl.order.dto.request.CancelOrderRequest;
import com.dgl.order.dto.request.CreateOrderRequest;
import com.dgl.order.dto.response.OrderResponse;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;

import java.util.UUID;

public interface OrderService {

    OrderResponse createOrder(CreateOrderRequest request, UUID correlationId);

    OrderResponse getOrderById(UUID id);

    OrderResponse getOrderByOrderNumber(String orderNumber);

    Page<OrderResponse> getOrdersByCustomer(UUID customerId, Pageable pageable);

    OrderResponse cancelOrder(UUID id, CancelOrderRequest request);

    OrderResponse updateOrderStatus(UUID id, OrderStatus newStatus, String failureReason);

    OrderResponse updateSagaStep(UUID id, String step, OrderStatus status, String failureReason);

    void handleInventoryReserved(UUID orderId);

    void handleInventoryFailed(UUID orderId, String reason);

    void handlePaymentAuthorized(UUID orderId);

    void handlePaymentFailed(UUID orderId, String reason);

    void handleShipmentCreated(UUID orderId);
 
    void handleSagaTimeout(UUID orderId);
}

