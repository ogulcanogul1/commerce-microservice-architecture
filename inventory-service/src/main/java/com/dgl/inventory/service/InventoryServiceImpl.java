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
import com.dgl.inventory.dto.request.ReserveStockRequest;
import com.dgl.inventory.dto.response.InventoryResponse;
import com.dgl.inventory.dto.response.ReservationResponse;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;

import java.util.List;
import java.util.UUID;

@Service
@RequiredArgsConstructor
public class InventoryServiceImpl implements InventoryService {

    private final CommandBus commandBus;
    private final QueryBus queryBus;

    @Override
    public InventoryResponse addStock(AddStockRequest request) {
        return commandBus.execute(new AddStockCommand(request));
    }

    @Override
    public InventoryResponse getInventoryBySku(String sku) {
        return queryBus.execute(new GetInventoryBySkuQuery(sku));
    }

    @Override
    public List<ReservationResponse> reserveStock(ReserveStockRequest request) {
        return commandBus.execute(new ReserveStockCommand(request));
    }

    @Override
    public void releaseStock(UUID orderId) {
        commandBus.execute(new ReleaseStockCommand(orderId));
    }

    @Override
    public void commitStock(UUID orderId) {
        commandBus.execute(new CommitStockCommand(orderId));
    }

    @Override
    public void expireReservations() {
        commandBus.execute(new ExpireReservationsCommand());
    }
}
