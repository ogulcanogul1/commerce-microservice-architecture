package com.dgl.order.controller;

import com.dgl.order.cqrs.CommandBus;
import com.dgl.order.cqrs.QueryBus;
import com.dgl.order.cqrs.command.CancelOrderCommand;
import com.dgl.order.cqrs.command.CreateOrderCommand;
import com.dgl.order.cqrs.command.UpdateOrderStatusCommand;
import com.dgl.order.cqrs.query.GetOrderByOrderNumberQuery;
import com.dgl.order.cqrs.query.GetOrderByIdQuery;
import com.dgl.order.cqrs.query.GetOrdersByCustomerQuery;
import com.dgl.order.domain.OrderStatus;
import com.dgl.order.dto.request.CancelOrderRequest;
import com.dgl.order.dto.request.CreateOrderRequest;
import com.dgl.order.dto.response.OrderResponse;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageImpl;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;

import java.util.List;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.*;

@ExtendWith(MockitoExtension.class)
class OrderControllerTest {

    @Mock
    private CommandBus commandBus;

    @Mock
    private QueryBus queryBus;

    @InjectMocks
    private OrderController orderController;

    private UUID orderId;
    private OrderResponse mockResponse;

    @BeforeEach
    void setUp() {
        orderId = UUID.randomUUID();
        mockResponse = mock(OrderResponse.class);
    }

    @Test
    @DisplayName("createOrder: Should dispatch CreateOrderCommand and return 201 CREATED")
    void createOrder_shouldDispatchCommandAndReturnCreated() {
        CreateOrderRequest request = new CreateOrderRequest(UUID.randomUUID(), List.of(), "Address", "TRY");
        UUID correlationId = UUID.randomUUID();

        when(commandBus.execute(any(CreateOrderCommand.class))).thenReturn(mockResponse);

        ResponseEntity<OrderResponse> response = orderController.createOrder(request, correlationId);

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.CREATED);
        assertThat(response.getBody()).isSameAs(mockResponse);
        verify(commandBus).execute(new CreateOrderCommand(request, correlationId));
    }

    @Test
    @DisplayName("getOrderById: Should dispatch GetOrderByIdQuery and return 200 OK")
    void getOrderById_shouldDispatchQueryAndReturnOk() {
        when(queryBus.execute(any(GetOrderByIdQuery.class))).thenReturn(mockResponse);

        ResponseEntity<OrderResponse> response = orderController.getOrderById(orderId);

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(response.getBody()).isSameAs(mockResponse);
        verify(queryBus).execute(new GetOrderByIdQuery(orderId));
    }

    @Test
    @DisplayName("getOrderByOrderNumber: Should dispatch GetOrderByOrderNumberQuery and return 200 OK")
    void getOrderByOrderNumber_shouldDispatchQueryAndReturnOk() {
        when(queryBus.execute(any(GetOrderByOrderNumberQuery.class))).thenReturn(mockResponse);

        ResponseEntity<OrderResponse> response = orderController.getOrderByOrderNumber("ORD-12345");

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(response.getBody()).isSameAs(mockResponse);
        verify(queryBus).execute(new GetOrderByOrderNumberQuery("ORD-12345"));
    }

    @Test
    @DisplayName("getOrdersByCustomer: Should dispatch GetOrdersByCustomerQuery and return 200 OK")
    void getOrdersByCustomer_shouldDispatchQueryAndReturnOk() {
        UUID customerId = UUID.randomUUID();
        Pageable pageable = PageRequest.of(0, 10);
        Page<OrderResponse> page = new PageImpl<>(List.of(mockResponse));

        when(queryBus.execute(any(GetOrdersByCustomerQuery.class))).thenReturn(page);

        ResponseEntity<Page<OrderResponse>> response = orderController.getOrdersByCustomer(customerId, pageable);

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(response.getBody()).isSameAs(page);
        verify(queryBus).execute(new GetOrdersByCustomerQuery(customerId, pageable));
    }

    @Test
    @DisplayName("cancelOrder: Should dispatch CancelOrderCommand and return 200 OK")
    void cancelOrder_shouldDispatchCommandAndReturnOk() {
        CancelOrderRequest request = new CancelOrderRequest("Reason");
        when(commandBus.execute(any(CancelOrderCommand.class))).thenReturn(mockResponse);

        ResponseEntity<OrderResponse> response = orderController.cancelOrder(orderId, request);

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(response.getBody()).isSameAs(mockResponse);
        verify(commandBus).execute(new CancelOrderCommand(orderId, request));
    }

    @Test
    @DisplayName("updateOrderStatus: Should dispatch UpdateOrderStatusCommand and return 200 OK")
    void updateOrderStatus_shouldDispatchCommandAndReturnOk() {
        when(commandBus.execute(any(UpdateOrderStatusCommand.class))).thenReturn(mockResponse);

        ResponseEntity<OrderResponse> response = orderController.updateOrderStatus(orderId, OrderStatus.CONFIRMED, "Reason");

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(response.getBody()).isSameAs(mockResponse);
        verify(commandBus).execute(new UpdateOrderStatusCommand(orderId, OrderStatus.CONFIRMED, "Reason"));
    }
}
