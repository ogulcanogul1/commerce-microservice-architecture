package com.dgl.order.cqrs.command;

import com.dgl.order.cqrs.Command;

import java.util.UUID;

/**
 * Command executed when shipment creation completes.
 */
public record HandleShipmentCreatedCommand(UUID orderId) implements Command<Void> {
}
