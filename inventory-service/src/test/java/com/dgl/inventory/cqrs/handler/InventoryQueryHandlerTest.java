package com.dgl.inventory.cqrs.handler;

import com.dgl.inventory.cqrs.mapper.InventoryResponseMapper;
import com.dgl.inventory.cqrs.query.GetInventoryBySkuQuery;
import com.dgl.inventory.domain.InventoryItem;
import com.dgl.inventory.dto.response.InventoryResponse;
import com.dgl.inventory.exception.InventoryNotFoundException;
import com.dgl.inventory.repository.InventoryItemRepository;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import java.util.Optional;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class InventoryQueryHandlerTest {

    @Mock
    private InventoryItemRepository inventoryRepository;

    private final InventoryResponseMapper responseMapper = new InventoryResponseMapper();

    private GetInventoryBySkuQueryHandler queryHandler;

    @BeforeEach
    void setUp() {
        queryHandler = new GetInventoryBySkuQueryHandler(inventoryRepository, responseMapper);
    }

    @Test
    @DisplayName("getInventoryBySku: Should return InventoryResponse when sku exists")
    void getInventoryBySku_existingSku_shouldReturnResponse() {
        InventoryItem item = InventoryItem.builder()
                .id(UUID.randomUUID())
                .sku("SKU-200")
                .totalQuantity(100)
                .reservedQuantity(25)
                .build();

        when(inventoryRepository.findBySku("SKU-200")).thenReturn(Optional.of(item));

        InventoryResponse response = queryHandler.handle(new GetInventoryBySkuQuery("SKU-200"));

        assertThat(response).isNotNull();
        assertThat(response.sku()).isEqualTo("SKU-200");
        assertThat(response.totalQuantity()).isEqualTo(100);
        assertThat(response.reservedQuantity()).isEqualTo(25);
        assertThat(response.availableQuantity()).isEqualTo(75);
    }

    @Test
    @DisplayName("getInventoryBySku: Should throw InventoryNotFoundException when sku not found")
    void getInventoryBySku_notFound_shouldThrowException() {
        when(inventoryRepository.findBySku("SKU-MISSING")).thenReturn(Optional.empty());

        assertThatThrownBy(() -> queryHandler.handle(new GetInventoryBySkuQuery("SKU-MISSING")))
                .isInstanceOf(InventoryNotFoundException.class);
    }
}
