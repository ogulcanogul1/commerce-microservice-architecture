package com.dgl.order.cqrs.command;

import com.dgl.order.cqrs.Command;

import java.util.UUID;

/**
 * Command executed when payment authorization succeeds.
 */
public record HandlePaymentAuthorizedCommand(UUID orderId) implements Command<Void> {
}
