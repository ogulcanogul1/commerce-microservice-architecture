package com.dgl.inventory.cqrs.handler;

import com.dgl.inventory.cqrs.CommandHandler;
import com.dgl.inventory.cqrs.command.ReleaseStockCommand;
import com.dgl.inventory.domain.InventoryItem;
import com.dgl.inventory.domain.ReservationStatus;
import com.dgl.inventory.domain.StockReservation;
import com.dgl.inventory.messaging.event.InventoryReleasedPayload;
import com.dgl.inventory.outbox.OutboxService;
import com.dgl.inventory.repository.StockReservationRepository;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;

import java.time.Instant;
import java.util.List;
import java.util.UUID;

@Component
@RequiredArgsConstructor
public class ReleaseStockCommandHandler implements CommandHandler<ReleaseStockCommand, Void> {

    private final StockReservationRepository reservationRepository;
    private final OutboxService outboxService;

    @Override
    @Transactional
    public Void handle(ReleaseStockCommand command) {
        UUID orderId = command.orderId();
        List<StockReservation> reservations = reservationRepository.findByOrderId(orderId);

        for (StockReservation res : reservations) {
            if (res.getStatus() == ReservationStatus.RESERVED) {
                InventoryItem item = res.getInventoryItem();
                item.setReservedQuantity(Math.max(0, item.getReservedQuantity() - res.getQuantity()));
                res.setStatus(ReservationStatus.RELEASED);
                res.setReleasedAt(Instant.now());
            }
        }

        if (!reservations.isEmpty()) {
            outboxService.recordEvent(
                    "Inventory",
                    orderId.toString(),
                    "InventoryReleased",
                    null,
                    null,
                    new InventoryReleasedPayload(orderId, "Stock released by order workflow")
            );
        }

        return null;
    }
}
