package com.dgl.order.cqrs.command;

import com.dgl.order.cqrs.Command;

import java.util.UUID;

/**
 * Command executed when an inventory reservation succeeds.
 */
public record HandleInventoryReservedCommand(UUID orderId) implements Command<Void> {
}
