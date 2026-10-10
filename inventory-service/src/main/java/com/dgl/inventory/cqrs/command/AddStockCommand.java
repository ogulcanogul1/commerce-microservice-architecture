package com.dgl.inventory.cqrs.command;

import com.dgl.inventory.cqrs.Command;
import com.dgl.inventory.dto.request.AddStockRequest;
import com.dgl.inventory.dto.response.InventoryResponse;

public record AddStockCommand(AddStockRequest request) implements Command<InventoryResponse> {
}
