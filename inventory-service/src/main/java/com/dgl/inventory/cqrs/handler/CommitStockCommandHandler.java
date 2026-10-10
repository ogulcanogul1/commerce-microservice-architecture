package com.dgl.inventory.cqrs.handler;

import com.dgl.inventory.cqrs.CommandHandler;
import com.dgl.inventory.cqrs.command.CommitStockCommand;
import com.dgl.inventory.domain.InventoryItem;
import com.dgl.inventory.domain.ReservationStatus;
import com.dgl.inventory.domain.StockReservation;
import com.dgl.inventory.repository.StockReservationRepository;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;

import java.time.Instant;
import java.util.List;
import java.util.UUID;

@Component
@RequiredArgsConstructor
public class CommitStockCommandHandler implements CommandHandler<CommitStockCommand, Void> {

    private final StockReservationRepository reservationRepository;

    @Override
    @Transactional
    public Void handle(CommitStockCommand command) {
        UUID orderId = command.orderId();
        List<StockReservation> reservations = reservationRepository.findByOrderId(orderId);

        for (StockReservation res : reservations) {
            if (res.getStatus() == ReservationStatus.RESERVED) {
                InventoryItem item = res.getInventoryItem();
                item.setTotalQuantity(Math.max(0, item.getTotalQuantity() - res.getQuantity()));
                item.setReservedQuantity(Math.max(0, item.getReservedQuantity() - res.getQuantity()));
                res.setStatus(ReservationStatus.COMMITTED);
                res.setCommittedAt(Instant.now());
            }
        }

        return null;
    }
}
