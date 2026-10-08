package com.dgl.inventory.config;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.stereotype.Component;

@Component
public class InventoryMetrics {

    private final Counter reservationsSuccessCounter;
    private final Counter reservationsFailedCounter;
    private final Counter reservationsReleasedCounter;
    private final Counter duplicateEventsCounter;
    private final Counter outboxPublishedCounter;
    private final Counter outboxFailedCounter;

    public InventoryMetrics(MeterRegistry registry) {
        this.reservationsSuccessCounter = Counter.builder("inventory.reserved.total")
                .description("Total number of successful stock reservations")
                .register(registry);

        this.reservationsFailedCounter = Counter.builder("inventory.out_of_stock.total")
                .description("Total number of failed stock reservations due to insufficient stock")
                .register(registry);

        this.reservationsReleasedCounter = Counter.builder("inventory.released.total")
                .description("Total number of released stock reservations")
                .register(registry);

        this.duplicateEventsCounter = Counter.builder("idempotent.duplicate.events.total")
                .tag("service", "inventory-service")
                .description("Total number of duplicate Kafka events intercepted")
                .register(registry);

        this.outboxPublishedCounter = Counter.builder("outbox.events.published.total")
                .tag("service", "inventory-service")
                .description("Total number of outbox events published to Kafka")
                .register(registry);

        this.outboxFailedCounter = Counter.builder("outbox.events.failed.total")
                .tag("service", "inventory-service")
                .description("Total number of outbox event publish failures")
                .register(registry);
    }

    public void incrementReserved() { reservationsSuccessCounter.increment(); }
    public void incrementFailed() { reservationsFailedCounter.increment(); }
    public void incrementReleased() { reservationsReleasedCounter.increment(); }
    public void incrementDuplicateEvents() { duplicateEventsCounter.increment(); }
    public void incrementOutboxPublished() { outboxPublishedCounter.increment(); }
    public void incrementOutboxFailed() { outboxFailedCounter.increment(); }
}
