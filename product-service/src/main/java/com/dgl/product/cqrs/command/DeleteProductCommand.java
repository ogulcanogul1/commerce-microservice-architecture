package com.dgl.product.cqrs.command;

import com.dgl.product.cqrs.Command;

import java.util.UUID;

public record DeleteProductCommand(UUID id) implements Command<Void> {
}
