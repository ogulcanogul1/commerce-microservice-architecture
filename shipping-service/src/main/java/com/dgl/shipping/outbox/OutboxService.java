package com.dgl.shipping.outbox;

import java.util.UUID;

public interface OutboxService {

    <T> void recordEvent(
            String aggregateType,
            String aggregateId,
            String eventType,
            UUID correlationId,
            UUID causationId,
            T payload
    );
}
