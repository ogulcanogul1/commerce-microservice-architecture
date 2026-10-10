package com.dgl.notification.cqrs.command;

import com.dgl.notification.cqrs.Command;

import java.util.UUID;

public record MarkEventProcessedCommand(String consumerGroup, UUID eventId, String eventType) implements Command<Void> {
}
