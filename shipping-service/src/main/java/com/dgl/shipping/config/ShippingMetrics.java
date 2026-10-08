package com.dgl.shipping.config;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.stereotype.Component;

@Component
public class ShippingMetrics {

    private final Counter shipmentsCreatedCounter;
    private final Counter shipmentsDeliveredCounter;
    private final Counter shipmentsCancelledCounter;
    private final Counter duplicateEventsCounter;
    private final Counter outboxPublishedCounter;
    private final Counter outboxFailedCounter;

    public ShippingMetrics(MeterRegistry registry) {
        this.shipmentsCreatedCounter = Counter.builder("shipments.created.total")
                .description("Total number of shipments created")
                .register(registry);

        this.shipmentsDeliveredCounter = Counter.builder("shipments.delivered.total")
                .description("Total number of shipments delivered")
                .register(registry);

        this.shipmentsCancelledCounter = Counter.builder("shipments.cancelled.total")
                .description("Total number of shipments cancelled")
                .register(registry);

        this.duplicateEventsCounter = Counter.builder("idempotent.duplicate.events.total")
                .tag("service", "shipping-service")
                .description("Total number of duplicate Kafka events intercepted")
                .register(registry);

        this.outboxPublishedCounter = Counter.builder("outbox.events.published.total")
                .tag("service", "shipping-service")
                .description("Total number of outbox events published to Kafka")
                .register(registry);

        this.outboxFailedCounter = Counter.builder("outbox.events.failed.total")
                .tag("service", "shipping-service")
                .description("Total number of outbox event publish failures")
                .register(registry);
    }

    public void incrementCreated() { shipmentsCreatedCounter.increment(); }
    public void incrementDelivered() { shipmentsDeliveredCounter.increment(); }
    public void incrementCancelled() { shipmentsCancelledCounter.increment(); }
    public void incrementDuplicateEvents() { duplicateEventsCounter.increment(); }
    public void incrementOutboxPublished() { outboxPublishedCounter.increment(); }
    public void incrementOutboxFailed() { outboxFailedCounter.increment(); }
}
