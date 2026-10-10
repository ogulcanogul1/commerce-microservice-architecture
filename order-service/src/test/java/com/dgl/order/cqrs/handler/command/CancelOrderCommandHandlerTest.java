package com.dgl.order.cqrs.handler.command;

import com.dgl.order.cqrs.command.CancelOrderCommand;
import com.dgl.order.cqrs.mapper.OrderResponseMapper;
import com.dgl.order.domain.Order;
import com.dgl.order.domain.OrderSagaState;
import com.dgl.order.domain.OrderStatus;
import com.dgl.order.dto.request.CancelOrderRequest;
import com.dgl.order.dto.response.OrderResponse;
import com.dgl.order.exception.InvalidOrderStateException;
import com.dgl.order.messaging.event.OrderCancelledPayload;
import com.dgl.order.outbox.OutboxService;
import com.dgl.order.repository.OrderRepository;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.Optional;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.ArgumentMatchers.isNull;
import static org.mockito.Mockito.*;

@ExtendWith(MockitoExtension.class)
class CancelOrderCommandHandlerTest {

    @Mock
    private OrderRepository orderRepository;

    @Mock
    private OutboxService outboxService;

    private CancelOrderCommandHandler handler;
    private final OrderResponseMapper orderResponseMapper = new OrderResponseMapper();

    private UUID orderId;
    private Order sampleOrder;

    @BeforeEach
    void setUp() {
        handler = new CancelOrderCommandHandler(orderRepository, outboxService, orderResponseMapper);
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
    @DisplayName("handle: Pending order should be marked CANCELLED and emit OrderCancelled outbox event")
    void handle_pendingOrder_shouldCancelAndEmitOutboxEvent() {
        when(orderRepository.findById(orderId)).thenReturn(Optional.of(sampleOrder));

        CancelOrderRequest cancelRequest = new CancelOrderRequest("Customer requested refund");
        OrderResponse response = handler.handle(new CancelOrderCommand(orderId, cancelRequest));

        assertThat(response.status()).isEqualTo(OrderStatus.CANCELLED);
        assertThat(response.failureReason()).isEqualTo("Customer requested refund");
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
    @DisplayName("handle: Confirmed order should throw InvalidOrderStateException")
    void handle_confirmedOrder_shouldThrowException() {
        sampleOrder.setStatus(OrderStatus.CONFIRMED);
        when(orderRepository.findById(orderId)).thenReturn(Optional.of(sampleOrder));

        CancelOrderRequest cancelRequest = new CancelOrderRequest("Customer changed mind");
        assertThatThrownBy(() -> handler.handle(new CancelOrderCommand(orderId, cancelRequest)))
                .isInstanceOf(InvalidOrderStateException.class)
                .hasMessageContaining("Confirmed order cannot be cancelled directly");

        verify(outboxService, never()).recordEvent(any(), any(), any(), any(), any(), any());
    }

    @Test
    @DisplayName("handle: Already cancelled order should return idempotently without duplicate outbox event")
    void handle_alreadyCancelledOrder_shouldReturnIdempotently() {
        sampleOrder.setStatus(OrderStatus.CANCELLED);
        sampleOrder.setFailureReason("Previous cancellation reason");
        when(orderRepository.findById(orderId)).thenReturn(Optional.of(sampleOrder));

        CancelOrderRequest cancelRequest = new CancelOrderRequest("Duplicate cancellation call");
        OrderResponse response = handler.handle(new CancelOrderCommand(orderId, cancelRequest));

        assertThat(response.status()).isEqualTo(OrderStatus.CANCELLED);
        assertThat(response.failureReason()).isEqualTo("Previous cancellation reason");
        verify(outboxService, never()).recordEvent(any(), any(), any(), any(), any(), any());
    }
}
