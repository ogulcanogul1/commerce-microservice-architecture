package com.dgl.shipping.cqrs.command;

import com.dgl.shipping.cqrs.Command;
import com.dgl.shipping.dto.request.UpdateShipmentStatusRequest;
import com.dgl.shipping.dto.response.ShipmentResponse;

import java.util.UUID;

public record UpdateShipmentStatusCommand(UUID id, UpdateShipmentStatusRequest request) implements Command<ShipmentResponse> {
}
