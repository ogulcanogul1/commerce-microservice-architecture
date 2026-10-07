package com.dgl.inventory.service;

import com.dgl.inventory.domain.InventoryItem;
import com.dgl.inventory.domain.ReservationStatus;
import com.dgl.inventory.domain.StockReservation;
import com.dgl.inventory.dto.request.AddStockRequest;
import com.dgl.inventory.dto.request.ReserveStockItem;
import com.dgl.inventory.dto.request.ReserveStockRequest;
import com.dgl.inventory.dto.response.InventoryResponse;
import com.dgl.inventory.dto.response.ReservationResponse;
import com.dgl.inventory.exception.InsufficientStockException;
import com.dgl.inventory.exception.InventoryNotFoundException;
import com.dgl.inventory.repository.InventoryItemRepository;
import com.dgl.inventory.repository.StockReservationRepository;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.Duration;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;

@Service
@RequiredArgsConstructor
@Transactional(readOnly = true)
public class InventoryServiceImpl implements InventoryService {

    private static final long DEFAULT_TTL_MINUTES = 15;

    private final InventoryItemRepository inventoryRepository;
    private final StockReservationRepository reservationRepository;

    @Override
    @Transactional
    public InventoryResponse addStock(AddStockRequest request) {
        InventoryItem item = inventoryRepository.findBySku(request.sku())
                .map(existing -> {
                    existing.setTotalQuantity(existing.getTotalQuantity() + request.quantity());
                    return existing;
                })
                .orElseGet(() -> InventoryItem.builder()
                        .sku(request.sku())
                        .totalQuantity(request.quantity())
                        .reservedQuantity(0)
                        .build());

        InventoryItem saved = inventoryRepository.save(item);
        return mapToResponse(saved);
    }

    @Override
    public InventoryResponse getInventoryBySku(String sku) {
        InventoryItem item = inventoryRepository.findBySku(sku)
                .orElseThrow(() -> new InventoryNotFoundException(sku));
        return mapToResponse(item);
    }

    @Override
    @Transactional
    public List<ReservationResponse> reserveStock(ReserveStockRequest request) {
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
        return savedReservations.stream().map(this::mapReservationToResponse).toList();
    }

    @Override
    @Transactional
    public void releaseStock(UUID orderId) {
        List<StockReservation> reservations = reservationRepository.findByOrderId(orderId);

        for (StockReservation res : reservations) {
            if (res.getStatus() == ReservationStatus.RESERVED) {
                InventoryItem item = res.getInventoryItem();
                item.setReservedQuantity(Math.max(0, item.getReservedQuantity() - res.getQuantity()));
                res.setStatus(ReservationStatus.RELEASED);
                res.setReleasedAt(Instant.now());
            }
        }
    }

    @Override
    @Transactional
    public void commitStock(UUID orderId) {
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
    }

    @Override
    @Transactional
    public void expireReservations() {
        List<StockReservation> expired = reservationRepository.findByStatusAndExpiresAtBefore(
                ReservationStatus.RESERVED, Instant.now());

        for (StockReservation res : expired) {
            InventoryItem item = res.getInventoryItem();
            item.setReservedQuantity(Math.max(0, item.getReservedQuantity() - res.getQuantity()));
            res.setStatus(ReservationStatus.RELEASED);
            res.setReleasedAt(Instant.now());
        }
    }

    private InventoryResponse mapToResponse(InventoryItem item) {
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

    private ReservationResponse mapReservationToResponse(StockReservation res) {
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
