package com.dgl.order.service;

import com.dgl.order.domain.Order;
import com.dgl.order.domain.OrderStatus;
import com.dgl.order.repository.OrderRepository;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.test.util.ReflectionTestUtils;

import java.time.Instant;
import java.util.List;
import java.util.UUID;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyCollection;
import static org.mockito.Mockito.*;

@ExtendWith(MockitoExtension.class)
class OrderSagaTimeoutWorkerTest {

    @Mock
    private OrderRepository orderRepository;

    @Mock
    private OrderService orderService;

    @InjectMocks
    private OrderSagaTimeoutWorker timeoutWorker;

    @BeforeEach
    void setUp() {
        ReflectionTestUtils.setField(timeoutWorker, "timeoutDurationSeconds", 300L);
    }

    @Test
    @DisplayName("processStuckSagas: Should invoke handleSagaTimeout for all stuck in-flight orders")
    void processStuckSagas_shouldTriggerCompensationForStuckOrders() {
        UUID orderId1 = UUID.randomUUID();
        UUID orderId2 = UUID.randomUUID();

        Order order1 = Order.builder().id(orderId1).orderNumber("ORD-001").status(OrderStatus.PENDING).build();
        Order order2 = Order.builder().id(orderId2).orderNumber("ORD-002").status(OrderStatus.INVENTORY_RESERVED).build();

        when(orderRepository.findByStatusInAndUpdatedAtBefore(anyCollection(), any(Instant.class)))
                .thenReturn(List.of(order1, order2));

        timeoutWorker.processStuckSagas();

        verify(orderService).handleSagaTimeout(orderId1);
        verify(orderService).handleSagaTimeout(orderId2);
    }

    @Test
    @DisplayName("processStuckSagas: Should do nothing when no stuck orders are found")
    void processStuckSagas_shouldDoNothingWhenNoStuckOrders() {
        when(orderRepository.findByStatusInAndUpdatedAtBefore(anyCollection(), any(Instant.class)))
                .thenReturn(List.of());

        timeoutWorker.processStuckSagas();

        verify(orderService, never()).handleSagaTimeout(any());
    }

    @Test
    @DisplayName("processStuckSagas: Should continue processing remaining orders if one throws exception")
    void processStuckSagas_shouldContinueProcessingWhenSingleOrderFails() {
        UUID orderId1 = UUID.randomUUID();
        UUID orderId2 = UUID.randomUUID();

        Order order1 = Order.builder().id(orderId1).orderNumber("ORD-001").status(OrderStatus.PENDING).build();
        Order order2 = Order.builder().id(orderId2).orderNumber("ORD-002").status(OrderStatus.PAYMENT_AUTHORIZED).build();

        when(orderRepository.findByStatusInAndUpdatedAtBefore(anyCollection(), any(Instant.class)))
                .thenReturn(List.of(order1, order2));

        doThrow(new RuntimeException("DB glitch")).when(orderService).handleSagaTimeout(orderId1);

        timeoutWorker.processStuckSagas();

        verify(orderService).handleSagaTimeout(orderId1);
        verify(orderService).handleSagaTimeout(orderId2);
    }
}
