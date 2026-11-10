package com.dgl.shipping.controller;

import com.dgl.shipping.cqrs.CommandBus;
import com.dgl.shipping.cqrs.QueryBus;
import com.dgl.shipping.cqrs.command.CancelShipmentCommand;
import com.dgl.shipping.cqrs.command.CreateShipmentCommand;
import com.dgl.shipping.cqrs.command.UpdateShipmentStatusCommand;
import com.dgl.shipping.cqrs.query.GetShipmentByIdQuery;
import com.dgl.shipping.cqrs.query.GetShipmentByOrderIdQuery;
import com.dgl.shipping.cqrs.query.TrackShipmentQuery;
import com.dgl.shipping.dto.request.CreateShipmentRequest;
import com.dgl.shipping.dto.request.UpdateShipmentStatusRequest;
import com.dgl.shipping.dto.response.ShipmentResponse;
import com.dgl.shipping.dto.response.TrackingResponse;
import com.dgl.shipping.exception.AccessDeniedException;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.responses.ApiResponses;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.Arrays;
import java.util.UUID;

@RestController
@RequestMapping("/api/v1/shipments")
@RequiredArgsConstructor
@Tag(name = "Shipping", description = "Endpoints for dispatching shipments, tracking parcels, and updating delivery status")
public class ShippingController {

    private final CommandBus commandBus;
    private final QueryBus queryBus;

    @PostMapping
    @Operation(summary = "Create shipment", description = "Initiates parcel shipment and generates tracking number")
    @ApiResponses({
            @ApiResponse(responseCode = "201", description = "Shipment created successfully"),
            @ApiResponse(responseCode = "400", description = "Invalid shipment details")
    })
    public ResponseEntity<ShipmentResponse> createShipment(@Valid @RequestBody CreateShipmentRequest request) {
        ShipmentResponse response = commandBus.execute(new CreateShipmentCommand(request));
        return ResponseEntity.status(HttpStatus.CREATED).body(response);
    }

    @GetMapping("/{id}")
    @Operation(summary = "Get shipment by ID", description = "Retrieves shipment by unique identifier")
    @ApiResponses({
            @ApiResponse(responseCode = "200", description = "Shipment found"),
            @ApiResponse(responseCode = "403", description = "Access denied: you do not have permission to view this shipment"),
            @ApiResponse(responseCode = "404", description = "Shipment not found")
    })
    public ResponseEntity<ShipmentResponse> getShipmentById(
            @PathVariable UUID id,
            @RequestHeader(value = "X-User-Id", required = false) String currentUserId,
            @RequestHeader(value = "X-User-Roles", required = false) String userRoles) {
        ShipmentResponse response = queryBus.execute(new GetShipmentByIdQuery(id));
        enforceOwnership(response.customerId(), currentUserId, userRoles);
        return ResponseEntity.ok(response);
    }

    @GetMapping("/order/{orderId}")
    @Operation(summary = "Get shipment by order ID", description = "Retrieves shipment linked to a specific order")
    @ApiResponses({
            @ApiResponse(responseCode = "200", description = "Shipment found"),
            @ApiResponse(responseCode = "403", description = "Access denied: you do not have permission to view this shipment"),
            @ApiResponse(responseCode = "404", description = "Shipment not found")
    })
    public ResponseEntity<ShipmentResponse> getShipmentByOrderId(
            @PathVariable UUID orderId,
            @RequestHeader(value = "X-User-Id", required = false) String currentUserId,
            @RequestHeader(value = "X-User-Roles", required = false) String userRoles) {
        ShipmentResponse response = queryBus.execute(new GetShipmentByOrderIdQuery(orderId));
        enforceOwnership(response.customerId(), currentUserId, userRoles);
        return ResponseEntity.ok(response);
    }

    @GetMapping("/track/{trackingNumber}")
    @Operation(summary = "Track parcel", description = "Fetches real-time status and delivery timeline by carrier tracking number")
    @ApiResponses({
            @ApiResponse(responseCode = "200", description = "Tracking information found"),
            @ApiResponse(responseCode = "404", description = "Tracking number not found")
    })
    public ResponseEntity<TrackingResponse> trackShipment(@PathVariable String trackingNumber) {
        TrackingResponse response = queryBus.execute(new TrackShipmentQuery(trackingNumber));
        return ResponseEntity.ok(response);
    }

    @PatchMapping("/{id}/status")
    @Operation(summary = "Update shipment status", description = "Carrier callback/webhook endpoint to advance delivery stage")
    @ApiResponses({
            @ApiResponse(responseCode = "200", description = "Status updated"),
            @ApiResponse(responseCode = "403", description = "Access denied: only administrators may update shipment status directly"),
            @ApiResponse(responseCode = "404", description = "Shipment not found")
    })
    public ResponseEntity<ShipmentResponse> updateShipmentStatus(
            @PathVariable UUID id,
            @Valid @RequestBody UpdateShipmentStatusRequest request,
            @RequestHeader(value = "X-User-Roles", required = false) String userRoles) {
        enforceAdmin(userRoles);
        ShipmentResponse response = commandBus.execute(new UpdateShipmentStatusCommand(id, request));
        return ResponseEntity.ok(response);
    }

    @PostMapping("/{id}/cancel")
    @Operation(summary = "Cancel shipment", description = "Compensating action to cancel delivery before dispatch")
    @ApiResponses({
            @ApiResponse(responseCode = "200", description = "Shipment cancelled"),
            @ApiResponse(responseCode = "400", description = "Shipment already delivered or cannot be cancelled"),
            @ApiResponse(responseCode = "403", description = "Access denied: you do not have permission to cancel this shipment"),
            @ApiResponse(responseCode = "404", description = "Shipment not found")
    })
    public ResponseEntity<ShipmentResponse> cancelShipment(
            @PathVariable UUID id,
            @RequestParam(required = false, defaultValue = "Cancelled by user/saga") String reason,
            @RequestHeader(value = "X-User-Id", required = false) String currentUserId,
            @RequestHeader(value = "X-User-Roles", required = false) String userRoles) {
        ShipmentResponse existing = queryBus.execute(new GetShipmentByIdQuery(id));
        enforceOwnership(existing.customerId(), currentUserId, userRoles);
        ShipmentResponse response = commandBus.execute(new CancelShipmentCommand(id, reason));
        return ResponseEntity.ok(response);
    }

    private void enforceOwnership(UUID resourceOwnerId, String currentUserId, String userRoles) {
        if (hasAdminRole(userRoles)) {
            return;
        }
        if (currentUserId == null || currentUserId.isBlank() || resourceOwnerId == null) {
            throw new AccessDeniedException("Access denied: caller identity is required");
        }
        if (!currentUserId.equalsIgnoreCase(resourceOwnerId.toString())) {
            throw new AccessDeniedException("Access denied: you do not have permission to view or modify this shipment");
        }
    }

    private void enforceAdmin(String userRoles) {
        if (!hasAdminRole(userRoles)) {
            throw new AccessDeniedException("Access denied: only administrators may update shipment status directly");
        }
    }

    private boolean hasAdminRole(String userRoles) {
        if (userRoles == null || userRoles.isBlank()) {
            return false;
        }
        return Arrays.stream(userRoles.split(","))
                .map(String::trim)
                .anyMatch("ROLE_ADMIN"::equalsIgnoreCase);
    }
}
