package com.dgl.inventory.cqrs.handler;

import com.dgl.inventory.cqrs.QueryHandler;
import com.dgl.inventory.cqrs.mapper.InventoryResponseMapper;
import com.dgl.inventory.cqrs.query.GetInventoryBySkuQuery;
import com.dgl.inventory.domain.InventoryItem;
import com.dgl.inventory.dto.response.InventoryResponse;
import com.dgl.inventory.exception.InventoryNotFoundException;
import com.dgl.inventory.repository.InventoryItemRepository;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;

@Component
@RequiredArgsConstructor
public class GetInventoryBySkuQueryHandler implements QueryHandler<GetInventoryBySkuQuery, InventoryResponse> {

    private final InventoryItemRepository inventoryRepository;
    private final InventoryResponseMapper responseMapper;

    @Override
    @Transactional(readOnly = true)
    public InventoryResponse handle(GetInventoryBySkuQuery query) {
        InventoryItem item = inventoryRepository.findBySku(query.sku())
                .orElseThrow(() -> new InventoryNotFoundException(query.sku()));
        return responseMapper.toResponse(item);
    }
}
