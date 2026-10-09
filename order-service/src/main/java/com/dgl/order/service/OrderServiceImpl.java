package com.dgl.order.service;

import com.dgl.order.domain.Order;
import com.dgl.order.domain.OrderItem;
import com.dgl.order.domain.OrderSagaState;
import com.dgl.order.domain.OrderStatus;
import com.dgl.order.dto.request.CancelOrderRequest;
import com.dgl.order.dto.request.CreateOrderItemRequest;
import com.dgl.order.dto.request.CreateOrderRequest;
import com.dgl.order.dto.response.OrderItemResponse;
import com.dgl.order.dto.response.OrderResponse;
import com.dgl.order.dto.response.OrderSagaStateResponse;
import com.dgl.order.exception.InvalidOrderStateException;
import com.dgl.order.exception.OrderNotFoundException;
import com.dgl.order.messaging.event.OrderCancelledPayload;
import com.dgl.order.messaging.event.OrderConfirmedPayload;
import com.dgl.order.messaging.event.OrderCreatedPayload;
import com.dgl.order.messaging.event.OrderItemPayload;
import com.dgl.order.outbox.OutboxService;
import com.dgl.order.repository.OrderRepository;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.UUID;

@Slf4j
@Service
@RequiredArgsConstructor
@Transactional(readOnly = true)
public class OrderServiceImpl implements OrderService {

    private final OrderRepository orderRepository;
    private final OutboxService outboxService;

    @org.springframework.beans.factory.annotation.Autowired(required = false)
    private com.dgl.order.config.OrderMetrics orderMetrics;

    @Override
    @Transactional
    public OrderResponse createOrder(CreateOrderRequest request, UUID correlationId) {
        UUID effectiveCorrelationId = correlationId != null ? correlationId : UUID.randomUUID();
        String orderNumber = "ORD-" + UUID.randomUUID().toString().substring(0, 8).toUpperCase();

        BigDecimal totalAmount = BigDecimal.ZERO;
        List<OrderItem> items = new ArrayList<>();

        Order order = Order.builder()
                .orderNumber(orderNumber)
                .customerId(request.customerId())
                .status(OrderStatus.PENDING)
                .currency(request.currency() != null ? request.currency() : "TRY")
                .shippingAddress(request.shippingAddress())
                .correlationId(effectiveCorrelationId)
                .items(items)
                .build();

        for (CreateOrderItemRequest itemReq : request.items()) {
            BigDecimal subtotal = itemReq.unitPrice().multiply(BigDecimal.valueOf(itemReq.quantity()));
            totalAmount = totalAmount.add(subtotal);

            OrderItem item = OrderItem.builder()
                    .order(order)
                    .sku(itemReq.sku())
                    .productName(itemReq.productName())
                    .unitPrice(itemReq.unitPrice())
                    .quantity(itemReq.quantity())
                    .subtotal(subtotal)
                    .build();
            items.add(item);
        }

        order.setTotalAmount(totalAmount);

        OrderSagaState sagaState = OrderSagaState.builder()
                .order(order)
                .currentStep("ORDER_CREATED")
                .build();
        order.setSagaState(sagaState);

        Order saved = orderRepository.save(order);

        List<OrderItemPayload> itemPayloads = order.getItems().stream()
                .map(i -> new OrderItemPayload(i.getSku(), i.getProductName(), i.getUnitPrice(), i.getQuantity()))
                .toList();

        OrderCreatedPayload createdPayload = new OrderCreatedPayload(
                saved.getId(),
                saved.getOrderNumber(),
                saved.getCustomerId(),
                saved.getTotalAmount(),
                saved.getCurrency(),
                saved.getShippingAddress(),
                itemPayloads
        );

        outboxService.recordEvent(
                "Order",
                saved.getId().toString(),
                "OrderCreated",
                saved.getCorrelationId(),
                null,
                createdPayload
        );

        if (orderMetrics != null) {
            orderMetrics.incrementOrdersCreated();
        }

        return mapToResponse(saved);
    }

    @Override
    public OrderResponse getOrderById(UUID id) {
        Order order = orderRepository.findById(id)
                .orElseThrow(() -> new OrderNotFoundException(id));
        return mapToResponse(order);
    }

    @Override
    public OrderResponse getOrderByOrderNumber(String orderNumber) {
        Order order = orderRepository.findByOrderNumber(orderNumber)
                .orElseThrow(() -> new OrderNotFoundException("Order not found with number: " + orderNumber));
        return mapToResponse(order);
    }

    @Override
    public Page<OrderResponse> getOrdersByCustomer(UUID customerId, Pageable pageable) {
        return orderRepository.findByCustomerId(customerId, pageable)
                .map(this::mapToResponse);
    }

    @Override
    @Transactional
    public OrderResponse cancelOrder(UUID id, CancelOrderRequest request) {
        Order order = orderRepository.findById(id)
                .orElseThrow(() -> new OrderNotFoundException(id));

        if (order.getStatus() == OrderStatus.CANCELLED) {
            return mapToResponse(order);
        }

        if (order.getStatus() == OrderStatus.CONFIRMED) {
            throw new InvalidOrderStateException("Confirmed order cannot be cancelled directly via standard cancel endpoint");
        }

        order.setStatus(OrderStatus.CANCELLED);
        order.setFailureReason(request.reason());

        if (order.getSagaState() != null) {
            order.getSagaState().setFailureStep(order.getSagaState().getCurrentStep());
            order.getSagaState().setFailureReason(request.reason());
            order.getSagaState().setCurrentStep("ORDER_CANCELLED");
        }

        outboxService.recordEvent(
                "Order",
                order.getId().toString(),
                "OrderCancelled",
                order.getCorrelationId(),
                null,
                new OrderCancelledPayload(order.getId(), order.getOrderNumber(), request.reason())
        );

        return mapToResponse(order);
    }

    @Override
    @Transactional
    public OrderResponse updateOrderStatus(UUID id, OrderStatus newStatus, String failureReason) {
        Order order = orderRepository.findById(id)
                .orElseThrow(() -> new OrderNotFoundException(id));

        order.setStatus(newStatus);
        if (failureReason != null) {
            order.setFailureReason(failureReason);
        }

        if (newStatus == OrderStatus.CONFIRMED) {
            outboxService.recordEvent(
                    "Order",
                    order.getId().toString(),
                    "OrderConfirmed",
                    order.getCorrelationId(),
                    null,
                    new OrderConfirmedPayload(order.getId(), order.getOrderNumber(), order.getCustomerId(), order.getTotalAmount())
            );
        } else if (newStatus == OrderStatus.CANCELLED) {
            outboxService.recordEvent(
                    "Order",
                    order.getId().toString(),
                    "OrderCancelled",
                    order.getCorrelationId(),
                    null,
                    new OrderCancelledPayload(order.getId(), order.getOrderNumber(), failureReason != null ? failureReason : "Order cancelled")
            );
        }

        return mapToResponse(order);
    }

    @Override
    @Transactional
    public OrderResponse updateSagaStep(UUID id, String step, OrderStatus status, String failureReason) {
        Order order = orderRepository.findById(id)
                .orElseThrow(() -> new OrderNotFoundException(id));

        order.setStatus(status);
        if (failureReason != null) {
            order.setFailureReason(failureReason);
        }

        OrderSagaState saga = order.getSagaState();
        if (saga != null) {
            saga.setCurrentStep(step);
            Instant now = Instant.now();
            switch (step) {
                case "INVENTORY_RESERVED" -> saga.setInventoryReservedAt(now);
                case "PAYMENT_AUTHORIZED" -> saga.setPaymentAuthorizedAt(now);
                case "SHIPPING_CREATED" -> saga.setShippingCreatedAt(now);
                default -> {}
            }
            if (failureReason != null) {
                saga.setFailureStep(step);
                saga.setFailureReason(failureReason);
            }
        }

        return mapToResponse(order);
    }

    @Override
    @Transactional
    public void handleInventoryReserved(UUID orderId) {
        Order order = orderRepository.findById(orderId)
                .orElseThrow(() -> new OrderNotFoundException(orderId));

        if (order.getStatus() == OrderStatus.CANCELLED) {
            return;
        }

        OrderSagaState saga = order.getSagaState();
        if (saga != null) {
            saga.setInventoryReservedAt(Instant.now());
            if (saga.getPaymentAuthorizedAt() != null) {
                // Both inventory and payment succeeded -> Order Confirmed!
                order.setStatus(OrderStatus.CONFIRMED);
                saga.setCurrentStep("CONFIRMED");
                outboxService.recordEvent(
                        "Order",
                        order.getId().toString(),
                        "OrderConfirmed",
                        order.getCorrelationId(),
                        null,
                        new OrderConfirmedPayload(order.getId(), order.getOrderNumber(), order.getCustomerId(), order.getTotalAmount())
                );
                if (orderMetrics != null) {
                    orderMetrics.incrementOrdersConfirmed();
                }
            } else {
                order.setStatus(OrderStatus.INVENTORY_RESERVED);
                saga.setCurrentStep("INVENTORY_RESERVED");
            }
        }
    }

    @Override
    @Transactional
    public void handleInventoryFailed(UUID orderId, String reason) {
        Order order = orderRepository.findById(orderId)
                .orElseThrow(() -> new OrderNotFoundException(orderId));

        if (order.getStatus() == OrderStatus.CANCELLED) {
            return;
        }

        String finalReason = reason != null ? reason : "Inventory reservation failed";
        order.setStatus(OrderStatus.CANCELLED);
        order.setFailureReason(finalReason);

        OrderSagaState saga = order.getSagaState();
        if (saga != null) {
            saga.setCurrentStep("INVENTORY_FAILED");
            saga.setFailureStep("INVENTORY_RESERVED");
            saga.setFailureReason(finalReason);
        }

        outboxService.recordEvent(
                "Order",
                order.getId().toString(),
                "OrderCancelled",
                order.getCorrelationId(),
                null,
                new OrderCancelledPayload(order.getId(), order.getOrderNumber(), finalReason)
        );

        if (orderMetrics != null) {
            orderMetrics.incrementOrdersCancelled();
        }
    }

    @Override
    @Transactional
    public void handlePaymentAuthorized(UUID orderId) {
        Order order = orderRepository.findById(orderId)
                .orElseThrow(() -> new OrderNotFoundException(orderId));

        if (order.getStatus() == OrderStatus.CANCELLED) {
            return;
        }

        OrderSagaState saga = order.getSagaState();
        if (saga != null) {
            saga.setPaymentAuthorizedAt(Instant.now());
            if (saga.getInventoryReservedAt() != null) {
                // Both inventory and payment succeeded -> Order Confirmed!
                order.setStatus(OrderStatus.CONFIRMED);
                saga.setCurrentStep("CONFIRMED");
                outboxService.recordEvent(
                        "Order",
                        order.getId().toString(),
                        "OrderConfirmed",
                        order.getCorrelationId(),
                        null,
                        new OrderConfirmedPayload(order.getId(), order.getOrderNumber(), order.getCustomerId(), order.getTotalAmount())
                );
                if (orderMetrics != null) {
                    orderMetrics.incrementOrdersConfirmed();
                }
            } else {
                order.setStatus(OrderStatus.PAYMENT_AUTHORIZED);
                saga.setCurrentStep("PAYMENT_AUTHORIZED");
            }
        }
    }

    @Override
    @Transactional
    public void handlePaymentFailed(UUID orderId, String reason) {
        Order order = orderRepository.findById(orderId)
                .orElseThrow(() -> new OrderNotFoundException(orderId));

        if (order.getStatus() == OrderStatus.CANCELLED) {
            return;
        }

        String finalReason = reason != null ? reason : "Payment authorization failed";
        order.setStatus(OrderStatus.CANCELLED);
        order.setFailureReason(finalReason);

        OrderSagaState saga = order.getSagaState();
        if (saga != null) {
            saga.setCurrentStep("PAYMENT_FAILED");
            saga.setFailureStep("PAYMENT_AUTHORIZED");
            saga.setFailureReason(finalReason);
        }

        outboxService.recordEvent(
                "Order",
                order.getId().toString(),
                "OrderCancelled",
                order.getCorrelationId(),
                null,
                new OrderCancelledPayload(order.getId(), order.getOrderNumber(), finalReason)
        );

        if (orderMetrics != null) {
            orderMetrics.incrementOrdersCancelled();
        }
    }

    @Override
    @Transactional
    public void handleShipmentCreated(UUID orderId) {
        Order order = orderRepository.findById(orderId)
                .orElseThrow(() -> new OrderNotFoundException(orderId));

        OrderSagaState saga = order.getSagaState();
        if (saga != null) {
            saga.setShippingCreatedAt(Instant.now());
            saga.setCurrentStep("SHIPPING_CREATED");
        }
        order.setStatus(OrderStatus.SHIPPING_CREATED);
    }

    @Override
    @Transactional
    public void handleSagaTimeout(UUID orderId) {
        Order order = orderRepository.findById(orderId)
                .orElseThrow(() -> new OrderNotFoundException(orderId));

        if (order.getStatus() == OrderStatus.CANCELLED || order.getStatus() == OrderStatus.CONFIRMED) {
            log.info("Order {} already in terminal state {}, skipping timeout cancellation", order.getId(), order.getStatus());
            return;
        }

        String timeoutReason = "Saga execution timed out after waiting for intermediate step completion";
        order.setStatus(OrderStatus.CANCELLED);
        order.setFailureReason(timeoutReason);

        OrderSagaState saga = order.getSagaState();
        if (saga != null) {
            saga.setFailureStep(saga.getCurrentStep());
            saga.setFailureReason(timeoutReason);
            saga.setCurrentStep("SAGA_TIMEOUT");
        }

        outboxService.recordEvent(
                "Order",
                order.getId().toString(),
                "OrderCancelled",
                order.getCorrelationId(),
                null,
                new OrderCancelledPayload(order.getId(), order.getOrderNumber(), timeoutReason)
        );

        if (orderMetrics != null) {
            orderMetrics.incrementOrdersCancelled();
            orderMetrics.incrementSagaTimeouts();
        }

        log.warn("Order {} (number={}) timed out during saga execution and was cancelled. Compensation event emitted.",
                order.getId(), order.getOrderNumber());
    }

    private OrderResponse mapToResponse(Order order) {
        List<OrderItemResponse> itemResponses = order.getItems() != null
                ? order.getItems().stream()
                .map(item -> new OrderItemResponse(
                        item.getId(),
                        item.getSku(),
                        item.getProductName(),
                        item.getUnitPrice(),
                        item.getQuantity(),
                        item.getSubtotal()
                ))
                .toList()
                : Collections.emptyList();

        OrderSagaStateResponse sagaResponse = null;
        if (order.getSagaState() != null) {
            OrderSagaState s = order.getSagaState();
            sagaResponse = new OrderSagaStateResponse(
                    s.getCurrentStep(),
                    s.getInventoryReservedAt(),
                    s.getPaymentAuthorizedAt(),
                    s.getShippingCreatedAt(),
                    s.getFailureStep(),
                    s.getFailureReason()
            );
        }

        return new OrderResponse(
                order.getId(),
                order.getOrderNumber(),
                order.getCustomerId(),
                order.getStatus(),
                order.getTotalAmount(),
                order.getCurrency(),
                order.getShippingAddress(),
                order.getFailureReason(),
                order.getCorrelationId(),
                itemResponses,
                sagaResponse,
                order.getCreatedAt(),
                order.getUpdatedAt()
        );
    }
}
