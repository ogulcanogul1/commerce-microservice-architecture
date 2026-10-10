package com.dgl.inventory.cqrs.command;

import com.dgl.inventory.cqrs.Command;

import java.util.UUID;

public record ReleaseStockCommand(UUID orderId) implements Command<Void> {
}
