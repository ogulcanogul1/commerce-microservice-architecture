package com.dgl.inventory.cqrs.query;

import com.dgl.inventory.cqrs.Query;
import com.dgl.inventory.dto.response.InventoryResponse;

public record GetInventoryBySkuQuery(String sku) implements Query<InventoryResponse> {
}
