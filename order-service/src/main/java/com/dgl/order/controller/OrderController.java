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
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.responses.ApiResponses;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.web.PageableDefault;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.UUID;

@RestController
@RequestMapping("/api/v1/orders")
@RequiredArgsConstructor
@Tag(name = "Orders", description = "Endpoints for placing orders, tracking order lifecycle, and managing cancellations")
public class OrderController {

    private final CommandBus commandBus;
    private final QueryBus queryBus;

    @PostMapping
    @Operation(summary = "Create an order", description = "Submits a new order and triggers the Saga workflow")
    @ApiResponses({
            @ApiResponse(responseCode = "201", description = "Order created and Saga initiated"),
            @ApiResponse(responseCode = "400", description = "Invalid order input"),
            @ApiResponse(responseCode = "403", description = "Access denied: cannot create order for another customer")
    })
    public ResponseEntity<OrderResponse> createOrder(
            @Valid @RequestBody CreateOrderRequest request,
            @RequestHeader(value = "X-User-Id", required = false) String currentUserId,
            @RequestHeader(value = "X-User-Roles", required = false) String userRoles,
            @Parameter(description = "Distributed trace correlation ID")
            @RequestHeader(value = "X-Correlation-Id", required = false) UUID correlationId) {
        enforceOwnership(request.customerId(), currentUserId, userRoles);
        OrderResponse response = commandBus.execute(new CreateOrderCommand(request, correlationId));
        return ResponseEntity.status(HttpStatus.CREATED).body(response);
    }

    @GetMapping("/{id}")
    @Operation(summary = "Get order by ID", description = "Retrieves order details and item lines by order UUID")
    @ApiResponses({
            @ApiResponse(responseCode = "200", description = "Order found"),
            @ApiResponse(responseCode = "403", description = "Access denied: cannot access another customer's order"),
            @ApiResponse(responseCode = "404", description = "Order not found")
    })
    public ResponseEntity<OrderResponse> getOrderById(
            @PathVariable UUID id,
            @RequestHeader(value = "X-User-Id", required = false) String currentUserId,
            @RequestHeader(value = "X-User-Roles", required = false) String userRoles) {
        OrderResponse order = queryBus.execute(new GetOrderByIdQuery(id));
        enforceOwnership(order.customerId(), currentUserId, userRoles);
        return ResponseEntity.ok(order);
    }

    @GetMapping("/by-number/{orderNumber}")
    @Operation(summary = "Get order by order number", description = "Retrieves order details using human-readable order code (e.g. ORD-xxx)")
    @ApiResponses({
            @ApiResponse(responseCode = "200", description = "Order found"),
            @ApiResponse(responseCode = "403", description = "Access denied: cannot access another customer's order"),
            @ApiResponse(responseCode = "404", description = "Order not found")
    })
    public ResponseEntity<OrderResponse> getOrderByOrderNumber(
            @PathVariable String orderNumber,
            @RequestHeader(value = "X-User-Id", required = false) String currentUserId,
            @RequestHeader(value = "X-User-Roles", required = false) String userRoles) {
        OrderResponse order = queryBus.execute(new GetOrderByOrderNumberQuery(orderNumber));
        enforceOwnership(order.customerId(), currentUserId, userRoles);
        return ResponseEntity.ok(order);
    }

    @GetMapping("/customer/{customerId}")
    @Operation(summary = "List customer orders", description = "Retrieves paginated orders placed by a specific customer")
    public ResponseEntity<Page<OrderResponse>> getOrdersByCustomer(
            @PathVariable UUID customerId,
            @RequestHeader(value = "X-User-Id", required = false) String currentUserId,
            @RequestHeader(value = "X-User-Roles", required = false) String userRoles,
            @PageableDefault(size = 20) Pageable pageable) {
        enforceOwnership(customerId, currentUserId, userRoles);
        return ResponseEntity.ok(queryBus.execute(new GetOrdersByCustomerQuery(customerId, pageable)));
    }

    @PostMapping("/{id}/cancel")
    @Operation(summary = "Cancel order", description = "Requests cancellation of an active order and initiates compensating Saga transactions")
    @ApiResponses({
            @ApiResponse(responseCode = "200", description = "Order cancelled"),
            @ApiResponse(responseCode = "400", description = "Order cannot be cancelled in its current state"),
            @ApiResponse(responseCode = "403", description = "Access denied: cannot cancel another customer's order"),
            @ApiResponse(responseCode = "404", description = "Order not found")
    })
    public ResponseEntity<OrderResponse> cancelOrder(
            @PathVariable UUID id,
            @Valid @RequestBody CancelOrderRequest request,
            @RequestHeader(value = "X-User-Id", required = false) String currentUserId,
            @RequestHeader(value = "X-User-Roles", required = false) String userRoles) {
        OrderResponse order = queryBus.execute(new GetOrderByIdQuery(id));
        enforceOwnership(order.customerId(), currentUserId, userRoles);
        return ResponseEntity.ok(commandBus.execute(new CancelOrderCommand(id, request)));
    }

    /**
     * Sipariş Sahipliği ve Yetki Denetimi (Fail-Closed Ownership Enforcement).
     *
     * Güvenlik İlkeleri:
     * 1. Yönetici İstisnası: 'ROLE_ADMIN' rolüne sahip çağrılar (admin paneli vb.) sahiplik kısıtlamasından muaftır.
     * 2. Varsayılan Olarak Kapalı (Fail-Closed): 'currentUserId' başlığı eksikse, boşsa veya siparişin sahibi
     *    (resourceOwnerId) veritabanında null ise istek ASLA geçirilmez; 403 AccessDeniedException fırlatılır.
     *    (Eski açık: header yokken 'null' geçip herkese izin veriyordu; bu açık kapatıldı).
     * 3. IDOR Engelleme: Oturum açan kullanıcının UUID'si ile siparişin sahibinin UUID'si eşleşmek zorundadır.
     */
    private void enforceOwnership(UUID resourceOwnerId, String currentUserId, String userRoles) {
        boolean isAdmin = userRoles != null && userRoles.contains("ROLE_ADMIN");
        if (isAdmin) {
            return;
        }
        // Fail-Closed Kuralı: Kimlik bilgisi eksikse veya sipariş sahibi belirsizse erişimi kesinlikle engelle
        if (currentUserId == null || currentUserId.isBlank() || resourceOwnerId == null) {
            throw new AccessDeniedException("Access denied: caller identity is required");
        }
        // Kullanıcı başkasına ait siparişi okumaya veya iptal etmeye çalışıyorsa engelle
        if (!currentUserId.equalsIgnoreCase(resourceOwnerId.toString())) {
            throw new AccessDeniedException("Access denied: you do not have permission to view or modify this order");
        }
    }

    @PatchMapping("/{id}/status")
    @Operation(summary = "Update order status", description = "Internal/Administrative endpoint to advance or reconcile order state")
    public ResponseEntity<OrderResponse> updateOrderStatus(
            @PathVariable UUID id,
            @RequestParam OrderStatus status,
            @RequestParam(required = false) String reason) {
        return ResponseEntity.ok(commandBus.execute(new UpdateOrderStatusCommand(id, status, reason)));
    }
}
