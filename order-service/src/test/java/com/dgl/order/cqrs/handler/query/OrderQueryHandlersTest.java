package com.dgl.order.cqrs.handler.query;

import com.dgl.order.cqrs.mapper.OrderResponseMapper;
import com.dgl.order.cqrs.query.GetOrderByOrderNumberQuery;
import com.dgl.order.cqrs.query.GetOrderByIdQuery;
import com.dgl.order.cqrs.query.GetOrdersByCustomerQuery;
import com.dgl.order.domain.Order;
import com.dgl.order.domain.OrderStatus;
import com.dgl.order.dto.response.OrderResponse;
import com.dgl.order.exception.OrderNotFoundException;
import com.dgl.order.repository.OrderRepository;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageImpl;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;

import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.List;
import java.util.Optional;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class OrderQueryHandlersTest {

    @Mock
    private OrderRepository orderRepository;

    private final OrderResponseMapper mapper = new OrderResponseMapper();

    private GetOrderByIdQueryHandler getOrderByIdHandler;
    private GetOrderByOrderNumberQueryHandler getOrderByOrderNumberHandler;
    private GetOrdersByCustomerQueryHandler getOrdersByCustomerHandler;

    private UUID orderId;
    private UUID customerId;
    private Order sampleOrder;

    @BeforeEach
    void setUp() {
        getOrderByIdHandler = new GetOrderByIdQueryHandler(orderRepository, mapper);
        getOrderByOrderNumberHandler = new GetOrderByOrderNumberQueryHandler(orderRepository, mapper);
        getOrdersByCustomerHandler = new GetOrdersByCustomerQueryHandler(orderRepository, mapper);

        orderId = UUID.randomUUID();
        customerId = UUID.randomUUID();

        sampleOrder = Order.builder()
                .id(orderId)
                .orderNumber("ORD-99999999")
                .customerId(customerId)
                .status(OrderStatus.CONFIRMED)
                .totalAmount(new BigDecimal("150.00"))
                .currency("TRY")
                .shippingAddress("Test Address")
                .correlationId(UUID.randomUUID())
                .items(new ArrayList<>())
                .build();
    }

    @Test
    @DisplayName("GetOrderById: Should return order response when found")
    void getOrderById_shouldReturnOrder() {
        when(orderRepository.findById(orderId)).thenReturn(Optional.of(sampleOrder));

        OrderResponse response = getOrderByIdHandler.handle(new GetOrderByIdQuery(orderId));

        assertThat(response).isNotNull();
        assertThat(response.id()).isEqualTo(orderId);
        assertThat(response.orderNumber()).isEqualTo("ORD-99999999");
    }

    @Test
    @DisplayName("GetOrderById: Should throw OrderNotFoundException when not found")
    void getOrderById_notFound_shouldThrowException() {
        when(orderRepository.findById(orderId)).thenReturn(Optional.empty());

        assertThatThrownBy(() -> getOrderByIdHandler.handle(new GetOrderByIdQuery(orderId)))
                .isInstanceOf(OrderNotFoundException.class);
    }

    @Test
    @DisplayName("GetOrderByOrderNumber: Should return order response when found")
    void getOrderByOrderNumber_shouldReturnOrder() {
        when(orderRepository.findByOrderNumber("ORD-99999999")).thenReturn(Optional.of(sampleOrder));

        OrderResponse response = getOrderByOrderNumberHandler.handle(new GetOrderByOrderNumberQuery("ORD-99999999"));

        assertThat(response).isNotNull();
        assertThat(response.orderNumber()).isEqualTo("ORD-99999999");
    }

    @Test
    @DisplayName("GetOrdersByCustomer: Should return paginated results")
    void getOrdersByCustomer_shouldReturnPaginatedOrders() {
        Pageable pageable = PageRequest.of(0, 10);
        when(orderRepository.findByCustomerId(customerId, pageable))
                .thenReturn(new PageImpl<>(List.of(sampleOrder), pageable, 1));

        Page<OrderResponse> result = getOrdersByCustomerHandler.handle(new GetOrdersByCustomerQuery(customerId, pageable));

        assertThat(result.getContent()).hasSize(1);
        assertThat(result.getContent().get(0).customerId()).isEqualTo(customerId);
    }
}
