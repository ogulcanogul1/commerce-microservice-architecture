package com.dgl.order.cqrs.command;

import com.dgl.order.cqrs.Command;

import java.util.UUID;

/**
 * Command executed when an inventory reservation fails.
 */
public record HandleInventoryFailedCommand(UUID orderId, String reason) implements Command<Void> {
}
