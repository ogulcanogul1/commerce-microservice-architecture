package com.dgl.product.cqrs.command;

import com.dgl.product.cqrs.Command;

import java.util.UUID;

public record DeleteCategoryCommand(UUID id) implements Command<Void> {
}
