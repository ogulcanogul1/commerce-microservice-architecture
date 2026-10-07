package com.dgl.inventory.controller;

import com.dgl.inventory.dto.request.AddStockRequest;
import com.dgl.inventory.dto.request.ReserveStockRequest;
import com.dgl.inventory.dto.response.InventoryResponse;
import com.dgl.inventory.dto.response.ReservationResponse;
import com.dgl.inventory.service.InventoryService;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;
import java.util.UUID;

@RestController
@RequestMapping("/api/v1/inventory")
@RequiredArgsConstructor
public class InventoryController {

    private final InventoryService inventoryService;

    @PostMapping("/stock")
    public ResponseEntity<InventoryResponse> addStock(@Valid @RequestBody AddStockRequest request) {
        InventoryResponse response = inventoryService.addStock(request);
        return ResponseEntity.status(HttpStatus.CREATED).body(response);
    }

    @GetMapping("/{sku}")
    public ResponseEntity<InventoryResponse> getInventoryBySku(@PathVariable String sku) {
        return ResponseEntity.ok(inventoryService.getInventoryBySku(sku));
    }

    @PostMapping("/reserve")
    public ResponseEntity<List<ReservationResponse>> reserveStock(@Valid @RequestBody ReserveStockRequest request) {
        List<ReservationResponse> response = inventoryService.reserveStock(request);
        return ResponseEntity.ok(response);
    }

    @PostMapping("/orders/{orderId}/release")
    public ResponseEntity<Void> releaseStock(@PathVariable UUID orderId) {
        inventoryService.releaseStock(orderId);
        return ResponseEntity.noContent().build();
    }

    @PostMapping("/orders/{orderId}/commit")
    public ResponseEntity<Void> commitStock(@PathVariable UUID orderId) {
        inventoryService.commitStock(orderId);
        return ResponseEntity.noContent().build();
    }
}
