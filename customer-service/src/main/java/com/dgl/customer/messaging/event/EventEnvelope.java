package com.dgl.customer.messaging.event;

import java.time.Instant;
import java.util.UUID;

public record EventEnvelope<T>(
    UUID eventId,
    String eventType,
    String aggregateId,
    String aggregateType,
    Instant timestamp,
    int version,
    UUID correlationId,
    UUID causationId,
    String traceparent,
    T payload
) {
    public static <T> EventEnvelope<T> of(String eventType, String aggregateId, String aggregateType, UUID correlationId, UUID causationId, T payload) {
        return of(eventType, aggregateId, aggregateType, correlationId, causationId, null, payload);
    }

    public static <T> EventEnvelope<T> of(String eventType, String aggregateId, String aggregateType, UUID correlationId, UUID causationId, String traceparent, T payload) {
        return new EventEnvelope<>(
            UUID.randomUUID(),
            eventType,
            aggregateId,
            aggregateType,
            Instant.now(),
            1,
            correlationId != null ? correlationId : UUID.randomUUID(),
            causationId,
            traceparent,
            payload
        );
    }
}
