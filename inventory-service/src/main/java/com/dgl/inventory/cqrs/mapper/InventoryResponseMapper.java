package com.dgl.inventory.cqrs.mapper;

import com.dgl.inventory.domain.InventoryItem;
import com.dgl.inventory.domain.StockReservation;
import com.dgl.inventory.dto.response.InventoryResponse;
import com.dgl.inventory.dto.response.ReservationResponse;
import org.springframework.stereotype.Component;

@Component
public class InventoryResponseMapper {

    public InventoryResponse toResponse(InventoryItem item) {
        if (item == null) {
            return null;
        }

        return new InventoryResponse(
                item.getId(),
                item.getSku(),
                item.getTotalQuantity(),
                item.getReservedQuantity(),
                item.getAvailableQuantity(),
                item.getCreatedAt(),
                item.getUpdatedAt()
        );
    }

    public ReservationResponse toReservationResponse(StockReservation res) {
        if (res == null) {
            return null;
        }

        return new ReservationResponse(
                res.getId(),
                res.getOrderId(),
                res.getInventoryItem().getSku(),
                res.getQuantity(),
                res.getStatus(),
                res.getExpiresAt(),
                res.getCreatedAt()
        );
    }
}
