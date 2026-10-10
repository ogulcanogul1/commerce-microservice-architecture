package com.dgl.notification.cqrs.query;

import com.dgl.notification.cqrs.Query;

import java.util.UUID;

public record IsEventProcessedQuery(String consumerGroup, UUID eventId) implements Query<Boolean> {
}
