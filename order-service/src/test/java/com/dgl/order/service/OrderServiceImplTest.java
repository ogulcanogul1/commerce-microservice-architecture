package com.dgl.order.service;

import com.dgl.order.domain.Order;
import com.dgl.order.domain.OrderItem;
import com.dgl.order.domain.OrderSagaState;
import com.dgl.order.domain.OrderStatus;
import com.dgl.order.dto.request.CancelOrderRequest;
import com.dgl.order.dto.request.CreateOrderItemRequest;
import com.dgl.order.dto.request.CreateOrderRequest;
import com.dgl.order.dto.response.OrderResponse;
import com.dgl.order.exception.InvalidOrderStateException;
import com.dgl.order.exception.OrderNotFoundException;
import com.dgl.order.messaging.event.OrderCancelledPayload;
import com.dgl.order.messaging.event.OrderConfirmedPayload;
import com.dgl.order.messaging.event.OrderCreatedPayload;
import com.dgl.order.outbox.OutboxService;
import com.dgl.order.repository.OrderRepository;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.Optional;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.*;

@ExtendWith(MockitoExtension.class)
class OrderServiceImplTest {

    @Mock
    private OrderRepository orderRepository;

    @Mock
    private OutboxService outboxService;

    @InjectMocks
    private OrderServiceImpl orderService;

    private UUID orderId;
    private UUID customerId;
    private Order sampleOrder;

    @BeforeEach
    void setUp() {
        orderId = UUID.randomUUID();
        customerId = UUID.randomUUID();

        sampleOrder = Order.builder()
                .id(orderId)
                .orderNumber("ORD-12345678")
                .customerId(customerId)
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
    @DisplayName("createOrder: Should calculate total amount, persist order and emit OrderCreated outbox event")
    void createOrder_shouldCalculateTotalAndEmitOutboxEvent() {
        CreateOrderItemRequest item1 = new CreateOrderItemRequest("SKU-1", "Product 1", new BigDecimal("100.00"), 2);
        CreateOrderItemRequest item2 = new CreateOrderItemRequest("SKU-2", "Product 2", new BigDecimal("50.00"), 1);

        CreateOrderRequest request = new CreateOrderRequest(
                customerId,
                List.of(item1, item2),
                "Kadıköy, İstanbul",
                "TRY"
        );

        when(orderRepository.save(any(Order.class))).thenAnswer(invocation -> {
            Order o = invocation.getArgument(0);
            o.setId(orderId);
            return o;
        });

        OrderResponse response = orderService.createOrder(request, UUID.randomUUID());

        assertThat(response).isNotNull();
        assertThat(response.id()).isEqualTo(orderId);
        assertThat(response.totalAmount()).isEqualByComparingTo(new BigDecimal("250.00"));
        assertThat(response.status()).isEqualTo(OrderStatus.PENDING);
        assertThat(response.items()).hasSize(2);

        verify(outboxService).recordEvent(
                eq("Order"),
                eq(orderId.toString()),
                eq("OrderCreated"),
                any(UUID.class),
                isNull(),
                any(OrderCreatedPayload.class)
        );
    }

    @Test
    @DisplayName("cancelOrder: Pending order should be marked CANCELLED and emit OrderCancelled outbox event")
    void cancelOrder_pendingOrder_shouldCancelAndEmitOutboxEvent() {
        when(orderRepository.findById(orderId)).thenReturn(Optional.of(sampleOrder));

        CancelOrderRequest cancelRequest = new CancelOrderRequest("Customer requested cancellation");
        OrderResponse response = orderService.cancelOrder(orderId, cancelRequest);

        assertThat(response.status()).isEqualTo(OrderStatus.CANCELLED);
        assertThat(response.failureReason()).isEqualTo("Customer requested cancellation");
        assertThat(sampleOrder.getSagaState().getCurrentStep()).isEqualTo("ORDER_CANCELLED");

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
    @DisplayName("cancelOrder: Confirmed order should throw InvalidOrderStateException")
    void cancelOrder_confirmedOrder_shouldThrowException() {
        sampleOrder.setStatus(OrderStatus.CONFIRMED);
        when(orderRepository.findById(orderId)).thenReturn(Optional.of(sampleOrder));

        CancelOrderRequest cancelRequest = new CancelOrderRequest("Late cancellation");

        assertThatThrownBy(() -> orderService.cancelOrder(orderId, cancelRequest))
                .isInstanceOf(InvalidOrderStateException.class)
                .hasMessageContaining("Confirmed order cannot be cancelled directly");

        verifyNoInteractions(outboxService);
    }

    @Test
    @DisplayName("handleInventoryReserved: When payment not yet authorized, should transition to INVENTORY_RESERVED")
    void handleInventoryReserved_whenPaymentNotAuthorized_shouldSetInventoryReserved() {
        when(orderRepository.findById(orderId)).thenReturn(Optional.of(sampleOrder));

        orderService.handleInventoryReserved(orderId);

        assertThat(sampleOrder.getStatus()).isEqualTo(OrderStatus.INVENTORY_RESERVED);
        assertThat(sampleOrder.getSagaState().getCurrentStep()).isEqualTo("INVENTORY_RESERVED");
        assertThat(sampleOrder.getSagaState().getInventoryReservedAt()).isNotNull();

        verify(outboxService, never()).recordEvent(any(), any(), eq("OrderConfirmed"), any(), any(), any());
    }

    @Test
    @DisplayName("handleInventoryReserved: When payment already authorized, should transition to CONFIRMED and emit OrderConfirmed")
    void handleInventoryReserved_whenPaymentAlreadyAuthorized_shouldConfirmOrder() {
        sampleOrder.getSagaState().setPaymentAuthorizedAt(Instant.now());
        when(orderRepository.findById(orderId)).thenReturn(Optional.of(sampleOrder));

        orderService.handleInventoryReserved(orderId);

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
    @DisplayName("handlePaymentAuthorized: When inventory already reserved, should transition to CONFIRMED and emit OrderConfirmed")
    void handlePaymentAuthorized_whenInventoryAlreadyReserved_shouldConfirmOrder() {
        sampleOrder.getSagaState().setInventoryReservedAt(Instant.now());
        when(orderRepository.findById(orderId)).thenReturn(Optional.of(sampleOrder));

        orderService.handlePaymentAuthorized(orderId);

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
    @DisplayName("handleInventoryFailed: Should cancel order and emit OrderCancelled outbox event")
    void handleInventoryFailed_shouldCancelOrderAndEmitOutboxEvent() {
        when(orderRepository.findById(orderId)).thenReturn(Optional.of(sampleOrder));

        orderService.handleInventoryFailed(orderId, "Product SKU-1 out of stock");

        assertThat(sampleOrder.getStatus()).isEqualTo(OrderStatus.CANCELLED);
        assertThat(sampleOrder.getFailureReason()).isEqualTo("Product SKU-1 out of stock");
        assertThat(sampleOrder.getSagaState().getCurrentStep()).isEqualTo("INVENTORY_FAILED");
        assertThat(sampleOrder.getSagaState().getFailureStep()).isEqualTo("INVENTORY_RESERVED");

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
    @DisplayName("handlePaymentFailed: Should cancel order and emit OrderCancelled outbox event")
    void handlePaymentFailed_shouldCancelOrderAndEmitOutboxEvent() {
        when(orderRepository.findById(orderId)).thenReturn(Optional.of(sampleOrder));

        orderService.handlePaymentFailed(orderId, "Insufficient credit card balance");

        assertThat(sampleOrder.getStatus()).isEqualTo(OrderStatus.CANCELLED);
        assertThat(sampleOrder.getFailureReason()).isEqualTo("Insufficient credit card balance");
        assertThat(sampleOrder.getSagaState().getCurrentStep()).isEqualTo("PAYMENT_FAILED");
        assertThat(sampleOrder.getSagaState().getFailureStep()).isEqualTo("PAYMENT_AUTHORIZED");

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
    @DisplayName("handleShipmentCreated: Should update saga state and order status to SHIPPING_CREATED")
    void handleShipmentCreated_shouldUpdateStatusToShippingCreated() {
        sampleOrder.setStatus(OrderStatus.CONFIRMED);
        when(orderRepository.findById(orderId)).thenReturn(Optional.of(sampleOrder));

        orderService.handleShipmentCreated(orderId);

        assertThat(sampleOrder.getStatus()).isEqualTo(OrderStatus.SHIPPING_CREATED);
        assertThat(sampleOrder.getSagaState().getCurrentStep()).isEqualTo("SHIPPING_CREATED");
        assertThat(sampleOrder.getSagaState().getShippingCreatedAt()).isNotNull();
    }
}
