package com.dgl.inventory.controller;

import com.dgl.inventory.cqrs.CommandBus;
import com.dgl.inventory.cqrs.QueryBus;
import com.dgl.inventory.cqrs.command.AddStockCommand;
import com.dgl.inventory.cqrs.command.CommitStockCommand;
import com.dgl.inventory.cqrs.command.ReleaseStockCommand;
import com.dgl.inventory.cqrs.command.ReserveStockCommand;
import com.dgl.inventory.cqrs.query.GetInventoryBySkuQuery;
import com.dgl.inventory.dto.request.AddStockRequest;
import com.dgl.inventory.dto.request.ReserveStockItem;
import com.dgl.inventory.dto.request.ReserveStockRequest;
import com.dgl.inventory.dto.response.InventoryResponse;
import com.dgl.inventory.dto.response.ReservationResponse;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;

import java.time.Instant;
import java.util.List;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class InventoryControllerTest {

    @Mock
    private CommandBus commandBus;

    @Mock
    private QueryBus queryBus;

    @InjectMocks
    private InventoryController controller;

    private InventoryResponse mockInventoryResponse;

    @BeforeEach
    void setUp() {
        mockInventoryResponse = new InventoryResponse(
                UUID.randomUUID(),
                "SKU-100",
                50,
                10,
                40,
                Instant.now(),
                Instant.now()
        );
    }

    @Test
    @DisplayName("addStock: Should dispatch command and return 201 Created")
    void addStock_shouldReturn201() {
        AddStockRequest request = new AddStockRequest("SKU-100", 50);
        when(commandBus.execute(any(AddStockCommand.class))).thenReturn(mockInventoryResponse);

        ResponseEntity<InventoryResponse> response = controller.addStock(request);

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.CREATED);
        assertThat(response.getBody()).isSameAs(mockInventoryResponse);
        verify(commandBus).execute(new AddStockCommand(request));
    }

    @Test
    @DisplayName("getInventoryBySku: Should dispatch query and return 200 OK")
    void getInventoryBySku_shouldReturn200() {
        when(queryBus.execute(any(GetInventoryBySkuQuery.class))).thenReturn(mockInventoryResponse);

        ResponseEntity<InventoryResponse> response = controller.getInventoryBySku("SKU-100");

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(response.getBody()).isSameAs(mockInventoryResponse);
        verify(queryBus).execute(new GetInventoryBySkuQuery("SKU-100"));
    }

    @Test
    @DisplayName("reserveStock: Should dispatch command and return 200 OK")
    void reserveStock_shouldReturn200() {
        UUID orderId = UUID.randomUUID();
        ReserveStockRequest request = new ReserveStockRequest(orderId, List.of(new ReserveStockItem("SKU-100", 5)), 15L);
        List<ReservationResponse> mockReservations = List.of();
        when(commandBus.execute(any(ReserveStockCommand.class))).thenReturn(mockReservations);

        ResponseEntity<List<ReservationResponse>> response = controller.reserveStock(request);

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(response.getBody()).isSameAs(mockReservations);
        verify(commandBus).execute(new ReserveStockCommand(request));
    }

    @Test
    @DisplayName("releaseStock: Should dispatch command and return 204 No Content")
    void releaseStock_shouldReturn204() {
        UUID orderId = UUID.randomUUID();

        ResponseEntity<Void> response = controller.releaseStock(orderId);

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.NO_CONTENT);
        verify(commandBus).execute(new ReleaseStockCommand(orderId));
    }

    @Test
    @DisplayName("commitStock: Should dispatch command and return 204 No Content")
    void commitStock_shouldReturn204() {
        UUID orderId = UUID.randomUUID();

        ResponseEntity<Void> response = controller.commitStock(orderId);

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.NO_CONTENT);
        verify(commandBus).execute(new CommitStockCommand(orderId));
    }
}
