package com.dgl.shipping.controller;

import com.dgl.shipping.dto.request.CreateShipmentRequest;
import com.dgl.shipping.dto.request.UpdateShipmentStatusRequest;
import com.dgl.shipping.dto.response.ShipmentResponse;
import com.dgl.shipping.dto.response.TrackingResponse;
import com.dgl.shipping.service.ShippingService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.responses.ApiResponses;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.UUID;

@RestController
@RequestMapping("/api/v1/shipments")
@RequiredArgsConstructor
@Tag(name = "Shipping", description = "Endpoints for dispatching shipments, tracking parcels, and updating delivery status")
public class ShippingController {

    private final ShippingService shippingService;

    @PostMapping
    @Operation(summary = "Create shipment", description = "Initiates parcel shipment and generates tracking number")
    @ApiResponses({
            @ApiResponse(responseCode = "201", description = "Shipment created successfully"),
            @ApiResponse(responseCode = "400", description = "Invalid shipment details")
    })
    public ResponseEntity<ShipmentResponse> createShipment(@Valid @RequestBody CreateShipmentRequest request) {
        ShipmentResponse response = shippingService.createShipment(request);
        return ResponseEntity.status(HttpStatus.CREATED).body(response);
    }

    @GetMapping("/{id}")
    @Operation(summary = "Get shipment by ID", description = "Retrieves shipment by unique identifier")
    @ApiResponses({
            @ApiResponse(responseCode = "200", description = "Shipment found"),
            @ApiResponse(responseCode = "404", description = "Shipment not found")
    })
    public ResponseEntity<ShipmentResponse> getShipmentById(@PathVariable UUID id) {
        return ResponseEntity.ok(shippingService.getShipmentById(id));
    }

    @GetMapping("/order/{orderId}")
    @Operation(summary = "Get shipment by order ID", description = "Retrieves shipment linked to a specific order")
    @ApiResponses({
            @ApiResponse(responseCode = "200", description = "Shipment found"),
            @ApiResponse(responseCode = "404", description = "Shipment not found")
    })
    public ResponseEntity<ShipmentResponse> getShipmentByOrderId(@PathVariable UUID orderId) {
        return ResponseEntity.ok(shippingService.getShipmentByOrderId(orderId));
    }

    @GetMapping("/track/{trackingNumber}")
    @Operation(summary = "Track parcel", description = "Fetches real-time status and delivery timeline by carrier tracking number")
    @ApiResponses({
            @ApiResponse(responseCode = "200", description = "Tracking information found"),
            @ApiResponse(responseCode = "404", description = "Tracking number not found")
    })
    public ResponseEntity<TrackingResponse> trackShipment(@PathVariable String trackingNumber) {
        return ResponseEntity.ok(shippingService.trackShipment(trackingNumber));
    }

    @PatchMapping("/{id}/status")
    @Operation(summary = "Update shipment status", description = "Carrier callback/webhook endpoint to advance delivery stage")
    @ApiResponses({
            @ApiResponse(responseCode = "200", description = "Status updated"),
            @ApiResponse(responseCode = "404", description = "Shipment not found")
    })
    public ResponseEntity<ShipmentResponse> updateShipmentStatus(
            @PathVariable UUID id,
            @Valid @RequestBody UpdateShipmentStatusRequest request) {
        return ResponseEntity.ok(shippingService.updateShipmentStatus(id, request));
    }

    @PostMapping("/{id}/cancel")
    @Operation(summary = "Cancel shipment", description = "Compensating action to cancel delivery before dispatch")
    @ApiResponses({
            @ApiResponse(responseCode = "200", description = "Shipment cancelled"),
            @ApiResponse(responseCode = "400", description = "Shipment already delivered or cannot be cancelled"),
            @ApiResponse(responseCode = "404", description = "Shipment not found")
    })
    public ResponseEntity<ShipmentResponse> cancelShipment(
            @PathVariable UUID id,
            @RequestParam(required = false, defaultValue = "Cancelled by user/saga") String reason) {
        return ResponseEntity.ok(shippingService.cancelShipment(id, reason));
    }
}
