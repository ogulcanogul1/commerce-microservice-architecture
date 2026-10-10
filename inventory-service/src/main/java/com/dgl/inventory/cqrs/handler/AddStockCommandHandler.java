package com.dgl.inventory.cqrs.handler;

import com.dgl.inventory.cqrs.CommandHandler;
import com.dgl.inventory.cqrs.command.AddStockCommand;
import com.dgl.inventory.cqrs.mapper.InventoryResponseMapper;
import com.dgl.inventory.domain.InventoryItem;
import com.dgl.inventory.dto.request.AddStockRequest;
import com.dgl.inventory.dto.response.InventoryResponse;
import com.dgl.inventory.repository.InventoryItemRepository;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;

@Component
@RequiredArgsConstructor
public class AddStockCommandHandler implements CommandHandler<AddStockCommand, InventoryResponse> {

    private final InventoryItemRepository inventoryRepository;
    private final InventoryResponseMapper responseMapper;

    @Override
    @Transactional
    public InventoryResponse handle(AddStockCommand command) {
        AddStockRequest request = command.request();
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
        return responseMapper.toResponse(saved);
    }
}
