package com.dgl.inventory.cqrs.handler;

import com.dgl.inventory.cqrs.CommandHandler;
import com.dgl.inventory.cqrs.command.ExpireReservationsCommand;
import com.dgl.inventory.domain.InventoryItem;
import com.dgl.inventory.domain.ReservationStatus;
import com.dgl.inventory.domain.StockReservation;
import com.dgl.inventory.repository.StockReservationRepository;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;

import java.time.Instant;
import java.util.List;

@Component
@RequiredArgsConstructor
public class ExpireReservationsCommandHandler implements CommandHandler<ExpireReservationsCommand, Void> {

    private final StockReservationRepository reservationRepository;

    @Override
    @Transactional
    public Void handle(ExpireReservationsCommand command) {
        List<StockReservation> expired = reservationRepository.findByStatusAndExpiresAtBefore(
                ReservationStatus.RESERVED, Instant.now());

        for (StockReservation res : expired) {
            InventoryItem item = res.getInventoryItem();
            item.setReservedQuantity(Math.max(0, item.getReservedQuantity() - res.getQuantity()));
            res.setStatus(ReservationStatus.RELEASED);
            res.setReleasedAt(Instant.now());
        }

        return null;
    }
}
