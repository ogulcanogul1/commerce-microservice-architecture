package com.dgl.order.controller;

import com.dgl.order.domain.OrderStatus;
import com.dgl.order.dto.request.CancelOrderRequest;
import com.dgl.order.dto.request.CreateOrderRequest;
import com.dgl.order.dto.response.OrderResponse;
import com.dgl.order.service.OrderService;
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

    private final OrderService orderService;

    @PostMapping
    @Operation(summary = "Create an order", description = "Submits a new order and triggers the Saga workflow")
    @ApiResponses({
            @ApiResponse(responseCode = "201", description = "Order created and Saga initiated"),
            @ApiResponse(responseCode = "400", description = "Invalid order input")
    })
    public ResponseEntity<OrderResponse> createOrder(
            @Valid @RequestBody CreateOrderRequest request,
            @Parameter(description = "Distributed trace correlation ID")
            @RequestHeader(value = "X-Correlation-Id", required = false) UUID correlationId) {
        OrderResponse response = orderService.createOrder(request, correlationId);
        return ResponseEntity.status(HttpStatus.CREATED).body(response);
    }

    @GetMapping("/{id}")
    @Operation(summary = "Get order by ID", description = "Retrieves order details and item lines by order UUID")
    @ApiResponses({
            @ApiResponse(responseCode = "200", description = "Order found"),
            @ApiResponse(responseCode = "404", description = "Order not found")
    })
    public ResponseEntity<OrderResponse> getOrderById(@PathVariable UUID id) {
        return ResponseEntity.ok(orderService.getOrderById(id));
    }

    @GetMapping("/by-number/{orderNumber}")
    @Operation(summary = "Get order by order number", description = "Retrieves order details using human-readable order code (e.g. ORD-xxx)")
    @ApiResponses({
            @ApiResponse(responseCode = "200", description = "Order found"),
            @ApiResponse(responseCode = "404", description = "Order not found")
    })
    public ResponseEntity<OrderResponse> getOrderByOrderNumber(@PathVariable String orderNumber) {
        return ResponseEntity.ok(orderService.getOrderByOrderNumber(orderNumber));
    }

    @GetMapping("/customer/{customerId}")
    @Operation(summary = "List customer orders", description = "Retrieves paginated orders placed by a specific customer")
    public ResponseEntity<Page<OrderResponse>> getOrdersByCustomer(
            @PathVariable UUID customerId,
            @PageableDefault(size = 20) Pageable pageable) {
        return ResponseEntity.ok(orderService.getOrdersByCustomer(customerId, pageable));
    }

    @PostMapping("/{id}/cancel")
    @Operation(summary = "Cancel order", description = "Requests cancellation of an active order and initiates compensating Saga transactions")
    @ApiResponses({
            @ApiResponse(responseCode = "200", description = "Order cancelled"),
            @ApiResponse(responseCode = "400", description = "Order cannot be cancelled in its current state"),
            @ApiResponse(responseCode = "404", description = "Order not found")
    })
    public ResponseEntity<OrderResponse> cancelOrder(
            @PathVariable UUID id,
            @Valid @RequestBody CancelOrderRequest request) {
        return ResponseEntity.ok(orderService.cancelOrder(id, request));
    }

    @PatchMapping("/{id}/status")
    @Operation(summary = "Update order status", description = "Internal/Administrative endpoint to advance or reconcile order state")
    public ResponseEntity<OrderResponse> updateOrderStatus(
            @PathVariable UUID id,
            @RequestParam OrderStatus status,
            @RequestParam(required = false) String reason) {
        return ResponseEntity.ok(orderService.updateOrderStatus(id, status, reason));
    }
}
