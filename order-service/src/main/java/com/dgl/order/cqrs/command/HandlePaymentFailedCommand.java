package com.dgl.order.cqrs.command;

import com.dgl.order.cqrs.Command;

import java.util.UUID;

/**
 * Command executed when payment authorization fails.
 */
public record HandlePaymentFailedCommand(UUID orderId, String reason) implements Command<Void> {
}
