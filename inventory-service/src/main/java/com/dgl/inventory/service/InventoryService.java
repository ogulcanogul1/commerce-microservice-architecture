package com.dgl.inventory.service;

import com.dgl.inventory.dto.request.AddStockRequest;
import com.dgl.inventory.dto.request.ReserveStockRequest;
import com.dgl.inventory.dto.response.InventoryResponse;
import com.dgl.inventory.dto.response.ReservationResponse;

import java.util.List;
import java.util.UUID;

public interface InventoryService {

    InventoryResponse addStock(AddStockRequest request);

    InventoryResponse getInventoryBySku(String sku);

    List<ReservationResponse> reserveStock(ReserveStockRequest request);

    void releaseStock(UUID orderId);

    void commitStock(UUID orderId);

    void expireReservations();
}
