package com.dgl.inventory.cqrs.command;

import com.dgl.inventory.cqrs.Command;
import com.dgl.inventory.dto.request.ReserveStockRequest;
import com.dgl.inventory.dto.response.ReservationResponse;

import java.util.List;

public record ReserveStockCommand(ReserveStockRequest request) implements Command<List<ReservationResponse>> {
}
