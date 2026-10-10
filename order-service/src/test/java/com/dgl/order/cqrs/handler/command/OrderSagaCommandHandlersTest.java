package com.dgl.order.cqrs.handler.command;

import com.dgl.order.cqrs.command.*;
import com.dgl.order.domain.Order;
import com.dgl.order.domain.OrderSagaState;
import com.dgl.order.domain.OrderStatus;
import com.dgl.order.messaging.event.OrderCancelledPayload;
import com.dgl.order.messaging.event.OrderConfirmedPayload;
import com.dgl.order.outbox.OutboxService;
import com.dgl.order.repository.OrderRepository;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.ArrayList;
import java.util.Optional;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.*;

@ExtendWith(MockitoExtension.class)
class OrderSagaCommandHandlersTest {

    @Mock
    private OrderRepository orderRepository;

    @Mock
    private OutboxService outboxService;

    private HandleInventoryReservedCommandHandler inventoryReservedHandler;
    private HandleInventoryFailedCommandHandler inventoryFailedHandler;
    private HandlePaymentAuthorizedCommandHandler paymentAuthorizedHandler;
    private HandlePaymentFailedCommandHandler paymentFailedHandler;
    private HandleShipmentCreatedCommandHandler shipmentCreatedHandler;
    private HandleSagaTimeoutCommandHandler sagaTimeoutHandler;

    private UUID orderId;
    private Order sampleOrder;

    @BeforeEach
    void setUp() {
        inventoryReservedHandler = new HandleInventoryReservedCommandHandler(orderRepository, outboxService);
        inventoryFailedHandler = new HandleInventoryFailedCommandHandler(orderRepository, outboxService);
        paymentAuthorizedHandler = new HandlePaymentAuthorizedCommandHandler(orderRepository, outboxService);
        paymentFailedHandler = new HandlePaymentFailedCommandHandler(orderRepository, outboxService);
        shipmentCreatedHandler = new HandleShipmentCreatedCommandHandler(orderRepository);
        sagaTimeoutHandler = new HandleSagaTimeoutCommandHandler(orderRepository, outboxService);

        orderId = UUID.randomUUID();
        sampleOrder = Order.builder()
                .id(orderId)
                .orderNumber("ORD-12345678")
                .customerId(UUID.randomUUID())
                .status(OrderStatus.PENDING)
                .totalAmount(new BigDecimal("250.00"))
                .currency("TRY")
                .shippingAddress("Bagdat Cad. No:1 Kadikoy Istanbul")
                .correlationId(UUID.randomUUID())
                .items(new ArrayList<>())
                .build();

        OrderSagaState sagaState = OrderSagaState.builder()
                .orderId(orderId)
                .order(sampleOrder)
                .currentStep("ORDER_CREATED")
                .build();
        sampleOrder.setSagaState(sagaState);
    }

    @Test
    @DisplayName("handleInventoryReserved: When payment not authorized, transition to INVENTORY_RESERVED")
    void handleInventoryReserved_whenPaymentNotAuthorized_shouldTransitionToInventoryReserved() {
        when(orderRepository.findById(orderId)).thenReturn(Optional.of(sampleOrder));

        inventoryReservedHandler.handle(new HandleInventoryReservedCommand(orderId));

        assertThat(sampleOrder.getStatus()).isEqualTo(OrderStatus.INVENTORY_RESERVED);
        assertThat(sampleOrder.getSagaState().getCurrentStep()).isEqualTo("INVENTORY_RESERVED");
        assertThat(sampleOrder.getSagaState().getInventoryReservedAt()).isNotNull();
        verify(outboxService, never()).recordEvent(any(), any(), any(), any(), any(), any());
    }

    @Test
    @DisplayName("handleInventoryReserved: When payment already authorized, transition to CONFIRMED and emit OrderConfirmed")
    void handleInventoryReserved_whenPaymentAuthorized_shouldTransitionToConfirmed() {
        sampleOrder.setStatus(OrderStatus.PAYMENT_AUTHORIZED);
        sampleOrder.getSagaState().setPaymentAuthorizedAt(Instant.now());
        when(orderRepository.findById(orderId)).thenReturn(Optional.of(sampleOrder));

        inventoryReservedHandler.handle(new HandleInventoryReservedCommand(orderId));

        assertThat(sampleOrder.getStatus()).isEqualTo(OrderStatus.CONFIRMED);
        assertThat(sampleOrder.getSagaState().getCurrentStep()).isEqualTo("CONFIRMED");
        verify(outboxService).recordEvent(
                eq("Order"),
                eq(orderId.toString()),
                eq("OrderConfirmed"),
                eq(sampleOrder.getCorrelationId()),
                isNull(),
                any(OrderConfirmedPayload.class)
        );
    }

    @Test
    @DisplayName("handlePaymentAuthorized: When inventory not reserved, transition to PAYMENT_AUTHORIZED")
    void handlePaymentAuthorized_whenInventoryNotReserved_shouldTransitionToPaymentAuthorized() {
        when(orderRepository.findById(orderId)).thenReturn(Optional.of(sampleOrder));

        paymentAuthorizedHandler.handle(new HandlePaymentAuthorizedCommand(orderId));

        assertThat(sampleOrder.getStatus()).isEqualTo(OrderStatus.PAYMENT_AUTHORIZED);
        assertThat(sampleOrder.getSagaState().getCurrentStep()).isEqualTo("PAYMENT_AUTHORIZED");
        assertThat(sampleOrder.getSagaState().getPaymentAuthorizedAt()).isNotNull();
        verify(outboxService, never()).recordEvent(any(), any(), any(), any(), any(), any());
    }

    @Test
    @DisplayName("handlePaymentAuthorized: When inventory already reserved, transition to CONFIRMED and emit event")
    void handlePaymentAuthorized_whenInventoryReserved_shouldTransitionToConfirmed() {
        sampleOrder.setStatus(OrderStatus.INVENTORY_RESERVED);
        sampleOrder.getSagaState().setInventoryReservedAt(Instant.now());
        when(orderRepository.findById(orderId)).thenReturn(Optional.of(sampleOrder));

        paymentAuthorizedHandler.handle(new HandlePaymentAuthorizedCommand(orderId));

        assertThat(sampleOrder.getStatus()).isEqualTo(OrderStatus.CONFIRMED);
        assertThat(sampleOrder.getSagaState().getCurrentStep()).isEqualTo("CONFIRMED");
        verify(outboxService).recordEvent(
                eq("Order"),
                eq(orderId.toString()),
                eq("OrderConfirmed"),
                eq(sampleOrder.getCorrelationId()),
                isNull(),
                any(OrderConfirmedPayload.class)
        );
    }

    @Test
    @DisplayName("handleInventoryFailed: Should cancel order and emit OrderCancelled event")
    void handleInventoryFailed_shouldCancelOrderAndEmitEvent() {
        when(orderRepository.findById(orderId)).thenReturn(Optional.of(sampleOrder));

        inventoryFailedHandler.handle(new HandleInventoryFailedCommand(orderId, "Out of stock"));

        assertThat(sampleOrder.getStatus()).isEqualTo(OrderStatus.CANCELLED);
        assertThat(sampleOrder.getFailureReason()).isEqualTo("Out of stock");
        verify(outboxService).recordEvent(
                eq("Order"),
                eq(orderId.toString()),
                eq("OrderCancelled"),
                eq(sampleOrder.getCorrelationId()),
                isNull(),
                any(OrderCancelledPayload.class)
        );
    }

    @Test
    @DisplayName("handlePaymentFailed: Should cancel order and emit OrderCancelled event")
    void handlePaymentFailed_shouldCancelOrderAndEmitEvent() {
        when(orderRepository.findById(orderId)).thenReturn(Optional.of(sampleOrder));

        paymentFailedHandler.handle(new HandlePaymentFailedCommand(orderId, "Card declined"));

        assertThat(sampleOrder.getStatus()).isEqualTo(OrderStatus.CANCELLED);
        assertThat(sampleOrder.getFailureReason()).isEqualTo("Card declined");
        verify(outboxService).recordEvent(
                eq("Order"),
                eq(orderId.toString()),
                eq("OrderCancelled"),
                eq(sampleOrder.getCorrelationId()),
                isNull(),
                any(OrderCancelledPayload.class)
        );
    }

    @Test
    @DisplayName("handleShipmentCreated: Should transition to SHIPPING_CREATED")
    void handleShipmentCreated_shouldTransitionToShippingCreated() {
        when(orderRepository.findById(orderId)).thenReturn(Optional.of(sampleOrder));

        shipmentCreatedHandler.handle(new HandleShipmentCreatedCommand(orderId));

        assertThat(sampleOrder.getStatus()).isEqualTo(OrderStatus.SHIPPING_CREATED);
        assertThat(sampleOrder.getSagaState().getCurrentStep()).isEqualTo("SHIPPING_CREATED");
        assertThat(sampleOrder.getSagaState().getShippingCreatedAt()).isNotNull();
    }

    @Test
    @DisplayName("handleSagaTimeout: Should cancel stuck order and emit compensation event")
    void handleSagaTimeout_shouldCancelStuckOrderAndEmitEvent() {
        sampleOrder.setStatus(OrderStatus.PENDING);
        when(orderRepository.findById(orderId)).thenReturn(Optional.of(sampleOrder));

        sagaTimeoutHandler.handle(new HandleSagaTimeoutCommand(orderId));

        assertThat(sampleOrder.getStatus()).isEqualTo(OrderStatus.CANCELLED);
        assertThat(sampleOrder.getSagaState().getCurrentStep()).isEqualTo("SAGA_TIMEOUT");
        verify(outboxService).recordEvent(
                eq("Order"),
                eq(orderId.toString()),
                eq("OrderCancelled"),
                eq(sampleOrder.getCorrelationId()),
                isNull(),
                any(OrderCancelledPayload.class)
        );
    }

    @Test
    @DisplayName("handleSagaTimeout: Already confirmed order should be ignored")
    void handleSagaTimeout_whenAlreadyConfirmed_shouldBeIgnored() {
        sampleOrder.setStatus(OrderStatus.CONFIRMED);
        when(orderRepository.findById(orderId)).thenReturn(Optional.of(sampleOrder));

        sagaTimeoutHandler.handle(new HandleSagaTimeoutCommand(orderId));

        assertThat(sampleOrder.getStatus()).isEqualTo(OrderStatus.CONFIRMED);
        verify(outboxService, never()).recordEvent(any(), any(), any(), any(), any(), any());
    }
}
