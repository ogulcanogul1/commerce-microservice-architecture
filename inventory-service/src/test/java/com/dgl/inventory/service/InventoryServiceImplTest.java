package com.dgl.inventory.service;

import com.dgl.inventory.cqrs.CommandBus;
import com.dgl.inventory.cqrs.QueryBus;
import com.dgl.inventory.cqrs.command.AddStockCommand;
import com.dgl.inventory.cqrs.command.CommitStockCommand;
import com.dgl.inventory.cqrs.command.ExpireReservationsCommand;
import com.dgl.inventory.cqrs.command.ReleaseStockCommand;
import com.dgl.inventory.cqrs.command.ReserveStockCommand;
import com.dgl.inventory.cqrs.query.GetInventoryBySkuQuery;
import com.dgl.inventory.dto.request.AddStockRequest;
import com.dgl.inventory.dto.request.ReserveStockItem;
import com.dgl.inventory.dto.request.ReserveStockRequest;
import com.dgl.inventory.dto.response.InventoryResponse;
import com.dgl.inventory.dto.response.ReservationResponse;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import java.time.Instant;
import java.util.List;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class InventoryServiceImplTest {

    @Mock
    private CommandBus commandBus;

    @Mock
    private QueryBus queryBus;

    @InjectMocks
    private InventoryServiceImpl inventoryService;

    @Test
    @DisplayName("addStock: Should delegate to command bus")
    void addStock_shouldDelegateToCommandBus() {
        AddStockRequest request = new AddStockRequest("SKU-1", 10);
        InventoryResponse expected = new InventoryResponse(UUID.randomUUID(), "SKU-1", 10, 0, 10, Instant.now(), Instant.now());
        when(commandBus.execute(any(AddStockCommand.class))).thenReturn(expected);

        InventoryResponse actual = inventoryService.addStock(request);

        assertThat(actual).isEqualTo(expected);
        verify(commandBus).execute(new AddStockCommand(request));
    }

    @Test
    @DisplayName("getInventoryBySku: Should delegate to query bus")
    void getInventoryBySku_shouldDelegateToQueryBus() {
        InventoryResponse expected = new InventoryResponse(UUID.randomUUID(), "SKU-1", 10, 0, 10, Instant.now(), Instant.now());
        when(queryBus.execute(any(GetInventoryBySkuQuery.class))).thenReturn(expected);

        InventoryResponse actual = inventoryService.getInventoryBySku("SKU-1");

        assertThat(actual).isEqualTo(expected);
        verify(queryBus).execute(new GetInventoryBySkuQuery("SKU-1"));
    }

    @Test
    @DisplayName("reserveStock: Should delegate to command bus")
    void reserveStock_shouldDelegateToCommandBus() {
        ReserveStockRequest request = new ReserveStockRequest(UUID.randomUUID(), List.of(new ReserveStockItem("SKU-1", 2)), 15L);
        List<ReservationResponse> expected = List.of();
        when(commandBus.execute(any(ReserveStockCommand.class))).thenReturn(expected);

        List<ReservationResponse> actual = inventoryService.reserveStock(request);

        assertThat(actual).isEqualTo(expected);
        verify(commandBus).execute(new ReserveStockCommand(request));
    }

    @Test
    @DisplayName("releaseStock: Should delegate to command bus")
    void releaseStock_shouldDelegateToCommandBus() {
        UUID orderId = UUID.randomUUID();

        inventoryService.releaseStock(orderId);

        verify(commandBus).execute(new ReleaseStockCommand(orderId));
    }

    @Test
    @DisplayName("commitStock: Should delegate to command bus")
    void commitStock_shouldDelegateToCommandBus() {
        UUID orderId = UUID.randomUUID();

        inventoryService.commitStock(orderId);

        verify(commandBus).execute(new CommitStockCommand(orderId));
    }

    @Test
    @DisplayName("expireReservations: Should delegate to command bus")
    void expireReservations_shouldDelegateToCommandBus() {
        inventoryService.expireReservations();

        verify(commandBus).execute(new ExpireReservationsCommand());
    }
}
