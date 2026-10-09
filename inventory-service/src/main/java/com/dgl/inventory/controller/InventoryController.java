package com.dgl.inventory.controller;

import com.dgl.inventory.dto.request.AddStockRequest;
import com.dgl.inventory.dto.request.ReserveStockRequest;
import com.dgl.inventory.dto.response.InventoryResponse;
import com.dgl.inventory.dto.response.ReservationResponse;
import com.dgl.inventory.service.InventoryService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.responses.ApiResponses;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.List;
import java.util.UUID;

@RestController
@RequestMapping("/api/v1/inventory")
@RequiredArgsConstructor
@Tag(name = "Inventory", description = "Endpoints for stock management, inventory reservations, commits, and releases")
public class InventoryController {

    private final InventoryService inventoryService;

    @PostMapping("/stock")
    @Operation(summary = "Add stock", description = "Increases available quantity or creates initial inventory for a SKU")
    @ApiResponses({
            @ApiResponse(responseCode = "201", description = "Stock added successfully"),
            @ApiResponse(responseCode = "400", description = "Invalid stock amount or SKU")
    })
    public ResponseEntity<InventoryResponse> addStock(@Valid @RequestBody AddStockRequest request) {
        InventoryResponse response = inventoryService.addStock(request);
        return ResponseEntity.status(HttpStatus.CREATED).body(response);
    }

    @GetMapping("/{sku}")
    @Operation(summary = "Get stock by SKU", description = "Fetches current stock quantities (available, reserved, total) for a SKU")
    @ApiResponses({
            @ApiResponse(responseCode = "200", description = "Inventory record found"),
            @ApiResponse(responseCode = "404", description = "SKU not found in inventory")
    })
    public ResponseEntity<InventoryResponse> getInventoryBySku(@PathVariable String sku) {
        return ResponseEntity.ok(inventoryService.getInventoryBySku(sku));
    }

    @PostMapping("/reserve")
    @Operation(summary = "Reserve stock", description = "Locks inventory for an order using optimistic locking and version check")
    @ApiResponses({
            @ApiResponse(responseCode = "200", description = "Stock reserved successfully"),
            @ApiResponse(responseCode = "400", description = "Insufficient stock or invalid items"),
            @ApiResponse(responseCode = "409", description = "Optimistic locking conflict")
    })
    public ResponseEntity<List<ReservationResponse>> reserveStock(@Valid @RequestBody ReserveStockRequest request) {
        List<ReservationResponse> response = inventoryService.reserveStock(request);
        return ResponseEntity.ok(response);
    }

    @PostMapping("/orders/{orderId}/release")
    @Operation(summary = "Release reserved stock", description = "Compensating action to release locked stock when an order is cancelled")
    @ApiResponses({
            @ApiResponse(responseCode = "204", description = "Stock released"),
            @ApiResponse(responseCode = "404", description = "Reservation not found")
    })
    public ResponseEntity<Void> releaseStock(@PathVariable UUID orderId) {
        inventoryService.releaseStock(orderId);
        return ResponseEntity.noContent().build();
    }

    @PostMapping("/orders/{orderId}/commit")
    @Operation(summary = "Commit reserved stock", description = "Permanently deducts reserved quantity upon successful payment and confirmation")
    @ApiResponses({
            @ApiResponse(responseCode = "204", description = "Stock committed"),
            @ApiResponse(responseCode = "404", description = "Reservation not found")
    })
    public ResponseEntity<Void> commitStock(@PathVariable UUID orderId) {
        inventoryService.commitStock(orderId);
        return ResponseEntity.noContent().build();
    }
}
