package com.dgl.order.cqrs.handler.command;

import com.dgl.order.cqrs.command.CreateOrderCommand;
import com.dgl.order.cqrs.mapper.OrderResponseMapper;
import com.dgl.order.domain.Order;
import com.dgl.order.domain.OrderStatus;
import com.dgl.order.dto.request.CreateOrderItemRequest;
import com.dgl.order.dto.request.CreateOrderRequest;
import com.dgl.order.dto.response.OrderResponse;
import com.dgl.order.messaging.event.OrderCreatedPayload;
import com.dgl.order.outbox.OutboxService;
import com.dgl.order.repository.OrderRepository;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import java.math.BigDecimal;
import java.util.List;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.ArgumentMatchers.isNull;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class CreateOrderCommandHandlerTest {

    @Mock
    private OrderRepository orderRepository;

    @Mock
    private OutboxService outboxService;

    private CreateOrderCommandHandler handler;
    private final OrderResponseMapper orderResponseMapper = new OrderResponseMapper();

    private UUID customerId;
    private UUID orderId;

    @BeforeEach
    void setUp() {
        handler = new CreateOrderCommandHandler(orderRepository, outboxService, orderResponseMapper);
        customerId = UUID.randomUUID();
        orderId = UUID.randomUUID();
    }

    @Test
    @DisplayName("handle: Should calculate total amount, persist order and emit OrderCreated outbox event")
    void handle_shouldCalculateTotalAndEmitOutboxEvent() {
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

        CreateOrderCommand command = new CreateOrderCommand(request, UUID.randomUUID());
        OrderResponse response = handler.handle(command);

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
}
