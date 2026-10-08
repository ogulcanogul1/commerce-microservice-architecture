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
import com.dgl.inventory.messaging.event.InventoryReleasedPayload;
import com.dgl.inventory.messaging.event.InventoryReservedPayload;
import com.dgl.inventory.outbox.OutboxService;
import com.dgl.inventory.repository.InventoryItemRepository;
import com.dgl.inventory.repository.StockReservationRepository;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import java.time.Instant;
import java.util.List;
import java.util.Optional;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.*;

@ExtendWith(MockitoExtension.class)
class InventoryServiceImplTest {

    @Mock
    private InventoryItemRepository inventoryRepository;

    @Mock
    private StockReservationRepository reservationRepository;

    @Mock
    private OutboxService outboxService;

    @InjectMocks
    private InventoryServiceImpl inventoryService;

    private InventoryItem sampleItem;

    @BeforeEach
    void setUp() {
        sampleItem = InventoryItem.builder()
                .id(UUID.randomUUID())
                .sku("SKU-100")
                .totalQuantity(50)
                .reservedQuantity(10)
                .build();
    }

    @Test
    @DisplayName("addStock: Should increase existing item total quantity")
    void addStock_existingItem_shouldIncreaseQuantity() {
        when(inventoryRepository.findBySku("SKU-100")).thenReturn(Optional.of(sampleItem));
        when(inventoryRepository.save(any(InventoryItem.class))).thenAnswer(i -> i.getArgument(0));

        AddStockRequest request = new AddStockRequest("SKU-100", 20);
        InventoryResponse response = inventoryService.addStock(request);

        assertThat(response.totalQuantity()).isEqualTo(70);
        assertThat(response.availableQuantity()).isEqualTo(60); // 70 - 10
    }

    @Test
    @DisplayName("reserveStock: Should successfully reserve stock and write InventoryReserved to outbox")
    void reserveStock_sufficientStock_shouldReserveAndEmitOutboxEvent() {
        when(inventoryRepository.findBySku("SKU-100")).thenReturn(Optional.of(sampleItem));
        when(reservationRepository.saveAll(anyList())).thenAnswer(i -> i.getArgument(0));

        UUID orderId = UUID.randomUUID();
        ReserveStockRequest request = new ReserveStockRequest(
                orderId,
                List.of(new ReserveStockItem("SKU-100", 15)),
                30L
        );

        List<ReservationResponse> responses = inventoryService.reserveStock(request);

        assertThat(responses).hasSize(1);
        assertThat(sampleItem.getReservedQuantity()).isEqualTo(25); // 10 + 15
        assertThat(sampleItem.getAvailableQuantity()).isEqualTo(25); // 50 - 25

        verify(outboxService).recordEvent(
                eq("Inventory"),
                eq(orderId.toString()),
                eq("InventoryReserved"),
                isNull(),
                isNull(),
                any(InventoryReservedPayload.class)
        );
    }

    @Test
    @DisplayName("reserveStock: Insufficient stock should throw InsufficientStockException without outbox event")
    void reserveStock_insufficientStock_shouldThrowException() {
        when(inventoryRepository.findBySku("SKU-100")).thenReturn(Optional.of(sampleItem));

        UUID orderId = UUID.randomUUID();
        ReserveStockRequest request = new ReserveStockRequest(
                orderId,
                List.of(new ReserveStockItem("SKU-100", 45)), // Available is 40 (50 - 10)
                30L
        );

        assertThatThrownBy(() -> inventoryService.reserveStock(request))
                .isInstanceOf(InsufficientStockException.class)
                .hasMessageContaining("Insufficient stock for SKU");

        verifyNoInteractions(outboxService);
    }

    @Test
    @DisplayName("reserveStock: Non-existent item should throw InventoryNotFoundException")
    void reserveStock_notFoundItem_shouldThrowException() {
        when(inventoryRepository.findBySku("NON-EXISTENT")).thenReturn(Optional.empty());

        ReserveStockRequest request = new ReserveStockRequest(
                UUID.randomUUID(),
                List.of(new ReserveStockItem("NON-EXISTENT", 5)),
                30L
        );

        assertThatThrownBy(() -> inventoryService.reserveStock(request))
                .isInstanceOf(InventoryNotFoundException.class);
    }

    @Test
    @DisplayName("releaseStock: Should restore reserved quantity and write InventoryReleased to outbox")
    void releaseStock_shouldRestoreQuantityAndEmitOutboxEvent() {
        UUID orderId = UUID.randomUUID();
        StockReservation reservation = StockReservation.builder()
                .id(UUID.randomUUID())
                .orderId(orderId)
                .inventoryItem(sampleItem)
                .quantity(10)
                .status(ReservationStatus.RESERVED)
                .build();

        when(reservationRepository.findByOrderId(orderId)).thenReturn(List.of(reservation));

        inventoryService.releaseStock(orderId);

        assertThat(sampleItem.getReservedQuantity()).isEqualTo(0);
        assertThat(reservation.getStatus()).isEqualTo(ReservationStatus.RELEASED);

        verify(outboxService).recordEvent(
                eq("Inventory"),
                eq(orderId.toString()),
                eq("InventoryReleased"),
                isNull(),
                isNull(),
                any(InventoryReleasedPayload.class)
        );
    }

    @Test
    @DisplayName("commitStock: Should reduce both total and reserved quantities")
    void commitStock_shouldReduceTotalAndReservedQuantities() {
        UUID orderId = UUID.randomUUID();
        StockReservation reservation = StockReservation.builder()
                .id(UUID.randomUUID())
                .orderId(orderId)
                .inventoryItem(sampleItem)
                .quantity(10)
                .status(ReservationStatus.RESERVED)
                .build();

        when(reservationRepository.findByOrderId(orderId)).thenReturn(List.of(reservation));

        inventoryService.commitStock(orderId);

        assertThat(sampleItem.getTotalQuantity()).isEqualTo(40); // 50 - 10
        assertThat(sampleItem.getReservedQuantity()).isEqualTo(0); // 10 - 10
        assertThat(reservation.getStatus()).isEqualTo(ReservationStatus.COMMITTED);
    }
}
