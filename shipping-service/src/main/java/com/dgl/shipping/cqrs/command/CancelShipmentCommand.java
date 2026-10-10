package com.dgl.shipping.cqrs.command;

import com.dgl.shipping.cqrs.Command;
import com.dgl.shipping.dto.response.ShipmentResponse;

import java.util.UUID;

public record CancelShipmentCommand(UUID id, String reason) implements Command<ShipmentResponse> {
}
