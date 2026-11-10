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
import com.dgl.order.exception.AccessDeniedException;
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
import static org.assertj.core.api.Assertions.assertThatThrownBy;
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
    private UUID customerId;
    private OrderResponse mockResponse;

    @BeforeEach
    void setUp() {
        orderId = UUID.randomUUID();
        customerId = UUID.randomUUID();
        mockResponse = mock(OrderResponse.class);
        lenient().when(mockResponse.customerId()).thenReturn(customerId);
    }

    @Test
    @DisplayName("createOrder: Should dispatch CreateOrderCommand and return 201 CREATED")
    void createOrder_shouldDispatchCommandAndReturnCreated() {
        CreateOrderRequest request = new CreateOrderRequest(customerId, List.of(), "Address", "TRY");
        UUID correlationId = UUID.randomUUID();

        when(commandBus.execute(any(CreateOrderCommand.class))).thenReturn(mockResponse);

        ResponseEntity<OrderResponse> response = orderController.createOrder(
                request, customerId.toString(), "ROLE_CUSTOMER", correlationId);

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.CREATED);
        assertThat(response.getBody()).isSameAs(mockResponse);
        verify(commandBus).execute(new CreateOrderCommand(request, correlationId));
    }

    @Test
    @DisplayName("createOrder: Should throw AccessDeniedException when customerId does not match current user header")
    void createOrder_shouldThrowAccessDenied_whenCustomerIdMismatch() {
        CreateOrderRequest request = new CreateOrderRequest(customerId, List.of(), "Address", "TRY");
        String attackerUserId = UUID.randomUUID().toString();

        assertThatThrownBy(() -> orderController.createOrder(
                request, attackerUserId, "ROLE_CUSTOMER", UUID.randomUUID()))
                .isInstanceOf(AccessDeniedException.class)
                .hasMessageContaining("Access denied");

        verifyNoInteractions(commandBus);
    }

    @Test
    @DisplayName("getOrderById: Should dispatch GetOrderByIdQuery and return 200 OK")
    void getOrderById_shouldDispatchQueryAndReturnOk() {
        when(queryBus.execute(any(GetOrderByIdQuery.class))).thenReturn(mockResponse);

        ResponseEntity<OrderResponse> response = orderController.getOrderById(
                orderId, customerId.toString(), "ROLE_CUSTOMER");

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(response.getBody()).isSameAs(mockResponse);
        verify(queryBus).execute(new GetOrderByIdQuery(orderId));
    }

    @Test
    @DisplayName("getOrderById: Should throw AccessDeniedException when requesting another customer's order")
    void getOrderById_shouldThrowAccessDenied_whenCustomerMismatch() {
        when(queryBus.execute(any(GetOrderByIdQuery.class))).thenReturn(mockResponse);
        String attackerUserId = UUID.randomUUID().toString();

        assertThatThrownBy(() -> orderController.getOrderById(
                orderId, attackerUserId, "ROLE_CUSTOMER"))
                .isInstanceOf(AccessDeniedException.class)
                .hasMessageContaining("Access denied");
    }

    @Test
    @DisplayName("getOrderById: Should throw AccessDeniedException when currentUserId header is missing or blank (fail-closed)")
    void getOrderById_shouldThrowAccessDenied_whenUserIdMissingOrBlank() {
        when(queryBus.execute(any(GetOrderByIdQuery.class))).thenReturn(mockResponse);

        assertThatThrownBy(() -> orderController.getOrderById(orderId, null, "ROLE_CUSTOMER"))
                .isInstanceOf(AccessDeniedException.class)
                .hasMessageContaining("caller identity is required");

        assertThatThrownBy(() -> orderController.getOrderById(orderId, "   ", "ROLE_CUSTOMER"))
                .isInstanceOf(AccessDeniedException.class)
                .hasMessageContaining("caller identity is required");
    }

    @Test
    @DisplayName("cancelOrder: Should throw AccessDeniedException when caller identity is missing")
    void cancelOrder_shouldThrowAccessDenied_whenUserIdMissing() {
        CancelOrderRequest request = new CancelOrderRequest("Reason");
        when(queryBus.execute(any(GetOrderByIdQuery.class))).thenReturn(mockResponse);

        assertThatThrownBy(() -> orderController.cancelOrder(orderId, request, null, "ROLE_CUSTOMER"))
                .isInstanceOf(AccessDeniedException.class)
                .hasMessageContaining("caller identity is required");

        verifyNoInteractions(commandBus);
    }

    @Test
    @DisplayName("getOrderById: Should allow admin to access any customer's order")
    void getOrderById_shouldAllowAdmin() {
        when(queryBus.execute(any(GetOrderByIdQuery.class))).thenReturn(mockResponse);
        String adminUserId = UUID.randomUUID().toString();

        ResponseEntity<OrderResponse> response = orderController.getOrderById(
                orderId, adminUserId, "ROLE_ADMIN");

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(response.getBody()).isSameAs(mockResponse);
    }

    @Test
    @DisplayName("getOrderById: Should deny user with role containing ROLE_ADMIN as substring (e.g. ROLE_ADMINISTRATOR)")
    void getOrderById_shouldDenyRoleAdministratorPrefixMatch() {
        when(queryBus.execute(any(GetOrderByIdQuery.class))).thenReturn(mockResponse);
        String attackerUserId = UUID.randomUUID().toString();

        assertThatThrownBy(() -> orderController.getOrderById(
                orderId, attackerUserId, "ROLE_ADMINISTRATOR"))
                .isInstanceOf(AccessDeniedException.class)
                .hasMessageContaining("you do not have permission");
    }

    @Test
    @DisplayName("getOrderByOrderNumber: Should dispatch GetOrderByOrderNumberQuery and return 200 OK")
    void getOrderByOrderNumber_shouldDispatchQueryAndReturnOk() {
        when(queryBus.execute(any(GetOrderByOrderNumberQuery.class))).thenReturn(mockResponse);

        ResponseEntity<OrderResponse> response = orderController.getOrderByOrderNumber(
                "ORD-12345", customerId.toString(), "ROLE_CUSTOMER");

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(response.getBody()).isSameAs(mockResponse);
        verify(queryBus).execute(new GetOrderByOrderNumberQuery("ORD-12345"));
    }

    @Test
    @DisplayName("getOrdersByCustomer: Should dispatch GetOrdersByCustomerQuery and return 200 OK")
    void getOrdersByCustomer_shouldDispatchQueryAndReturnOk() {
        Pageable pageable = PageRequest.of(0, 10);
        Page<OrderResponse> page = new PageImpl<>(List.of(mockResponse));

        when(queryBus.execute(any(GetOrdersByCustomerQuery.class))).thenReturn(page);

        ResponseEntity<Page<OrderResponse>> response = orderController.getOrdersByCustomer(
                customerId, customerId.toString(), "ROLE_CUSTOMER", pageable);

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(response.getBody()).isSameAs(page);
        verify(queryBus).execute(new GetOrdersByCustomerQuery(customerId, pageable));
    }

    @Test
    @DisplayName("cancelOrder: Should dispatch CancelOrderCommand and return 200 OK")
    void cancelOrder_shouldDispatchCommandAndReturnOk() {
        CancelOrderRequest request = new CancelOrderRequest("Reason");
        when(queryBus.execute(any(GetOrderByIdQuery.class))).thenReturn(mockResponse);
        when(commandBus.execute(any(CancelOrderCommand.class))).thenReturn(mockResponse);

        ResponseEntity<OrderResponse> response = orderController.cancelOrder(
                orderId, request, customerId.toString(), "ROLE_CUSTOMER");

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(response.getBody()).isSameAs(mockResponse);
        verify(commandBus).execute(new CancelOrderCommand(orderId, request));
    }

    @Test
    @DisplayName("updateOrderStatus: Should dispatch UpdateOrderStatusCommand when caller is admin")
    void updateOrderStatus_shouldDispatchCommandAndReturnOk() {
        when(commandBus.execute(any(UpdateOrderStatusCommand.class))).thenReturn(mockResponse);

        ResponseEntity<OrderResponse> response = orderController.updateOrderStatus(
                orderId, OrderStatus.CONFIRMED, "Reason", "ROLE_ADMIN");

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(response.getBody()).isSameAs(mockResponse);
        verify(commandBus).execute(new UpdateOrderStatusCommand(orderId, OrderStatus.CONFIRMED, "Reason"));
    }

    @Test
    @DisplayName("updateOrderStatus: Should throw AccessDeniedException when caller is not admin")
    void updateOrderStatus_shouldThrowAccessDeniedWhenNotAdmin() {
        assertThatThrownBy(() -> orderController.updateOrderStatus(
                orderId, OrderStatus.CONFIRMED, "Reason", "ROLE_USER"))
                .isInstanceOf(AccessDeniedException.class)
                .hasMessageContaining("only administrators may update order status directly");

        assertThatThrownBy(() -> orderController.updateOrderStatus(
                orderId, OrderStatus.CONFIRMED, "Reason", null))
                .isInstanceOf(AccessDeniedException.class)
                .hasMessageContaining("only administrators may update order status directly");
    }
}
