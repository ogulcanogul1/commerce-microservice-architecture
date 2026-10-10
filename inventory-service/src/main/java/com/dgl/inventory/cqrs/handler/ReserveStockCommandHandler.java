package com.dgl.inventory.cqrs.handler;

import com.dgl.inventory.cqrs.CommandHandler;
import com.dgl.inventory.cqrs.command.ReserveStockCommand;
import com.dgl.inventory.cqrs.mapper.InventoryResponseMapper;
import com.dgl.inventory.domain.InventoryItem;
import com.dgl.inventory.domain.ReservationStatus;
import com.dgl.inventory.domain.StockReservation;
import com.dgl.inventory.dto.request.ReserveStockItem;
import com.dgl.inventory.dto.request.ReserveStockRequest;
import com.dgl.inventory.dto.response.ReservationResponse;
import com.dgl.inventory.exception.InsufficientStockException;
import com.dgl.inventory.exception.InventoryNotFoundException;
import com.dgl.inventory.messaging.event.InventoryReservedPayload;
import com.dgl.inventory.messaging.event.ReservedItemPayload;
import com.dgl.inventory.outbox.OutboxService;
import com.dgl.inventory.repository.InventoryItemRepository;
import com.dgl.inventory.repository.StockReservationRepository;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;

import java.time.Duration;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;

@Component
@RequiredArgsConstructor
public class ReserveStockCommandHandler implements CommandHandler<ReserveStockCommand, List<ReservationResponse>> {

    private static final long DEFAULT_TTL_MINUTES = 15;

    private final InventoryItemRepository inventoryRepository;
    private final StockReservationRepository reservationRepository;
    private final OutboxService outboxService;
    private final InventoryResponseMapper responseMapper;

    @Override
    @Transactional(noRollbackFor = {InsufficientStockException.class, InventoryNotFoundException.class})
    public List<ReservationResponse> handle(ReserveStockCommand command) {
        ReserveStockRequest request = command.request();
        long ttlMinutes = request.ttlMinutes() != null ? request.ttlMinutes() : DEFAULT_TTL_MINUTES;
        Instant expiresAt = Instant.now().plus(Duration.ofMinutes(ttlMinutes));

        List<StockReservation> reservations = new ArrayList<>();

        for (ReserveStockItem itemRequest : request.items()) {
            InventoryItem item = inventoryRepository.findBySku(itemRequest.sku())
                    .orElseThrow(() -> new InventoryNotFoundException(itemRequest.sku()));

            if (item.getAvailableQuantity() < itemRequest.quantity()) {
                throw new InsufficientStockException(item.getSku(), itemRequest.quantity(), item.getAvailableQuantity());
            }

            item.setReservedQuantity(item.getReservedQuantity() + itemRequest.quantity());

            StockReservation reservation = StockReservation.builder()
                    .orderId(request.orderId())
                    .inventoryItem(item)
                    .quantity(itemRequest.quantity())
                    .status(ReservationStatus.RESERVED)
                    .expiresAt(expiresAt)
                    .build();

            reservations.add(reservation);
        }

        List<StockReservation> savedReservations = reservationRepository.saveAll(reservations);

        List<ReservedItemPayload> reservedPayloads = request.items().stream()
                .map(i -> new ReservedItemPayload(i.sku(), i.quantity()))
                .toList();

        outboxService.recordEvent(
                "Inventory",
                request.orderId().toString(),
                "InventoryReserved",
                null,
                null,
                new InventoryReservedPayload(request.orderId(), reservedPayloads)
        );

        return savedReservations.stream().map(responseMapper::toReservationResponse).toList();
    }
}
