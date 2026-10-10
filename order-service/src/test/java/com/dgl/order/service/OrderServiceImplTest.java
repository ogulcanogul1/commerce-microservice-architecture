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

import java.util.List;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.*;

@ExtendWith(MockitoExtension.class)
class OrderServiceImplTest {

    @Mock
    private CommandBus commandBus;

    @Mock
    private QueryBus queryBus;

    @InjectMocks
    private OrderServiceImpl orderService;

    @Test
    @DisplayName("createOrder: Should dispatch CreateOrderCommand to CommandBus")
    void createOrder_shouldDispatchToCommandBus() {
        CreateOrderRequest request = new CreateOrderRequest(UUID.randomUUID(), List.of(), "Address", "TRY");
        UUID correlationId = UUID.randomUUID();
        OrderResponse expected = mock(OrderResponse.class);

        when(commandBus.execute(any(CreateOrderCommand.class))).thenReturn(expected);

        OrderResponse actual = orderService.createOrder(request, correlationId);

        assertThat(actual).isSameAs(expected);
        verify(commandBus).execute(any(CreateOrderCommand.class));
    }

    @Test
    @DisplayName("getOrderById: Should dispatch GetOrderByIdQuery to QueryBus")
    void getOrderById_shouldDispatchToQueryBus() {
        UUID orderId = UUID.randomUUID();
        OrderResponse expected = mock(OrderResponse.class);

        when(queryBus.execute(any(GetOrderByIdQuery.class))).thenReturn(expected);

        OrderResponse actual = orderService.getOrderById(orderId);

        assertThat(actual).isSameAs(expected);
        verify(queryBus).execute(new GetOrderByIdQuery(orderId));
    }

    @Test
    @DisplayName("getOrderByOrderNumber: Should dispatch GetOrderByOrderNumberQuery to QueryBus")
    void getOrderByOrderNumber_shouldDispatchToQueryBus() {
        OrderResponse expected = mock(OrderResponse.class);

        when(queryBus.execute(any(GetOrderByOrderNumberQuery.class))).thenReturn(expected);

        OrderResponse actual = orderService.getOrderByOrderNumber("ORD-123");

        assertThat(actual).isSameAs(expected);
        verify(queryBus).execute(new GetOrderByOrderNumberQuery("ORD-123"));
    }

    @Test
    @DisplayName("getOrdersByCustomer: Should dispatch GetOrdersByCustomerQuery to QueryBus")
    void getOrdersByCustomer_shouldDispatchToQueryBus() {
        UUID customerId = UUID.randomUUID();
        Pageable pageable = PageRequest.of(0, 10);
        Page<OrderResponse> expected = new PageImpl<>(List.of());

        when(queryBus.execute(any(GetOrdersByCustomerQuery.class))).thenReturn(expected);

        Page<OrderResponse> actual = orderService.getOrdersByCustomer(customerId, pageable);

        assertThat(actual).isSameAs(expected);
        verify(queryBus).execute(new GetOrdersByCustomerQuery(customerId, pageable));
    }

    @Test
    @DisplayName("cancelOrder: Should dispatch CancelOrderCommand to CommandBus")
    void cancelOrder_shouldDispatchToCommandBus() {
        UUID orderId = UUID.randomUUID();
        CancelOrderRequest request = new CancelOrderRequest("Reason");
        OrderResponse expected = mock(OrderResponse.class);

        when(commandBus.execute(any(CancelOrderCommand.class))).thenReturn(expected);

        OrderResponse actual = orderService.cancelOrder(orderId, request);

        assertThat(actual).isSameAs(expected);
        verify(commandBus).execute(new CancelOrderCommand(orderId, request));
    }

    @Test
    @DisplayName("updateOrderStatus: Should dispatch UpdateOrderStatusCommand to CommandBus")
    void updateOrderStatus_shouldDispatchToCommandBus() {
        UUID orderId = UUID.randomUUID();
        OrderResponse expected = mock(OrderResponse.class);

        when(commandBus.execute(any(UpdateOrderStatusCommand.class))).thenReturn(expected);

        OrderResponse actual = orderService.updateOrderStatus(orderId, OrderStatus.CONFIRMED, null);

        assertThat(actual).isSameAs(expected);
        verify(commandBus).execute(new UpdateOrderStatusCommand(orderId, OrderStatus.CONFIRMED, null));
    }

    @Test
    @DisplayName("updateSagaStep: Should dispatch UpdateSagaStepCommand to CommandBus")
    void updateSagaStep_shouldDispatchToCommandBus() {
        UUID orderId = UUID.randomUUID();
        OrderResponse expected = mock(OrderResponse.class);

        when(commandBus.execute(any(UpdateSagaStepCommand.class))).thenReturn(expected);

        OrderResponse actual = orderService.updateSagaStep(orderId, "STEP", OrderStatus.PENDING, null);

        assertThat(actual).isSameAs(expected);
        verify(commandBus).execute(new UpdateSagaStepCommand(orderId, "STEP", OrderStatus.PENDING, null));
    }

    @Test
    @DisplayName("handleInventoryReserved: Should dispatch HandleInventoryReservedCommand to CommandBus")
    void handleInventoryReserved_shouldDispatchToCommandBus() {
        UUID orderId = UUID.randomUUID();

        orderService.handleInventoryReserved(orderId);

        verify(commandBus).execute(new HandleInventoryReservedCommand(orderId));
    }

    @Test
    @DisplayName("handleInventoryFailed: Should dispatch HandleInventoryFailedCommand to CommandBus")
    void handleInventoryFailed_shouldDispatchToCommandBus() {
        UUID orderId = UUID.randomUUID();

        orderService.handleInventoryFailed(orderId, "Fail reason");

        verify(commandBus).execute(new HandleInventoryFailedCommand(orderId, "Fail reason"));
    }

    @Test
    @DisplayName("handlePaymentAuthorized: Should dispatch HandlePaymentAuthorizedCommand to CommandBus")
    void handlePaymentAuthorized_shouldDispatchToCommandBus() {
        UUID orderId = UUID.randomUUID();

        orderService.handlePaymentAuthorized(orderId);

        verify(commandBus).execute(new HandlePaymentAuthorizedCommand(orderId));
    }

    @Test
    @DisplayName("handlePaymentFailed: Should dispatch HandlePaymentFailedCommand to CommandBus")
    void handlePaymentFailed_shouldDispatchToCommandBus() {
        UUID orderId = UUID.randomUUID();

        orderService.handlePaymentFailed(orderId, "Payment declined");

        verify(commandBus).execute(new HandlePaymentFailedCommand(orderId, "Payment declined"));
    }

    @Test
    @DisplayName("handleShipmentCreated: Should dispatch HandleShipmentCreatedCommand to CommandBus")
    void handleShipmentCreated_shouldDispatchToCommandBus() {
        UUID orderId = UUID.randomUUID();

        orderService.handleShipmentCreated(orderId);

        verify(commandBus).execute(new HandleShipmentCreatedCommand(orderId));
    }

    @Test
    @DisplayName("handleSagaTimeout: Should dispatch HandleSagaTimeoutCommand to CommandBus")
    void handleSagaTimeout_shouldDispatchToCommandBus() {
        UUID orderId = UUID.randomUUID();

        orderService.handleSagaTimeout(orderId);

        verify(commandBus).execute(new HandleSagaTimeoutCommand(orderId));
    }
}
