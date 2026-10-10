package com.dgl.shipping.cqrs.command;

import com.dgl.shipping.cqrs.Command;
import com.dgl.shipping.dto.request.CreateShipmentRequest;
import com.dgl.shipping.dto.response.ShipmentResponse;

public record CreateShipmentCommand(CreateShipmentRequest request) implements Command<ShipmentResponse> {
}
