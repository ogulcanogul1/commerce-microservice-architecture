package com.dgl.shipping.service;

import com.dgl.shipping.cqrs.CommandBus;
import com.dgl.shipping.cqrs.QueryBus;
import com.dgl.shipping.cqrs.command.CancelShipmentCommand;
import com.dgl.shipping.cqrs.command.CreateShipmentCommand;
import com.dgl.shipping.cqrs.command.UpdateShipmentStatusCommand;
import com.dgl.shipping.cqrs.query.GetShipmentByIdQuery;
import com.dgl.shipping.cqrs.query.GetShipmentByOrderIdQuery;
import com.dgl.shipping.cqrs.query.TrackShipmentQuery;
import com.dgl.shipping.dto.request.CreateShipmentRequest;
import com.dgl.shipping.dto.request.UpdateShipmentStatusRequest;
import com.dgl.shipping.dto.response.ShipmentResponse;
import com.dgl.shipping.dto.response.TrackingResponse;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;

import java.util.UUID;

@Service
@RequiredArgsConstructor
public class ShippingServiceImpl implements ShippingService {

    private final CommandBus commandBus;
    private final QueryBus queryBus;

    @Override
    public ShipmentResponse createShipment(CreateShipmentRequest request) {
        return commandBus.execute(new CreateShipmentCommand(request));
    }

    @Override
    public ShipmentResponse getShipmentById(UUID id) {
        return queryBus.execute(new GetShipmentByIdQuery(id));
    }

    @Override
    public ShipmentResponse getShipmentByOrderId(UUID orderId) {
        return queryBus.execute(new GetShipmentByOrderIdQuery(orderId));
    }

    @Override
    public TrackingResponse trackShipment(String trackingNumber) {
        return queryBus.execute(new TrackShipmentQuery(trackingNumber));
    }

    @Override
    public ShipmentResponse updateShipmentStatus(UUID id, UpdateShipmentStatusRequest request) {
        return commandBus.execute(new UpdateShipmentStatusCommand(id, request));
    }

    @Override
    public ShipmentResponse cancelShipment(UUID id, String reason) {
        return commandBus.execute(new CancelShipmentCommand(id, reason));
    }
}
