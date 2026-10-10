package com.dgl.order.cqrs.command;

import com.dgl.order.cqrs.Command;

import java.util.UUID;

/**
 * Command executed when a Saga workflow times out while waiting for a response.
 */
public record HandleSagaTimeoutCommand(UUID orderId) implements Command<Void> {
}
