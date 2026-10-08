package com.dgl.customer.config;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.stereotype.Component;

@Component
public class CustomerMetrics {

    private final Counter customersCreatedCounter;
    private final Counter customersUpdatedCounter;
    private final Counter outboxPublishedCounter;
    private final Counter outboxFailedCounter;

    public CustomerMetrics(MeterRegistry registry) {
        this.customersCreatedCounter = Counter.builder("customers.created.total")
                .description("Total number of customers created")
                .register(registry);

        this.customersUpdatedCounter = Counter.builder("customers.updated.total")
                .description("Total number of customers updated")
                .register(registry);

        this.outboxPublishedCounter = Counter.builder("outbox.events.published.total")
                .tag("service", "customer-service")
                .description("Total number of outbox events published to Kafka")
                .register(registry);

        this.outboxFailedCounter = Counter.builder("outbox.events.failed.total")
                .tag("service", "customer-service")
                .description("Total number of outbox event publish failures")
                .register(registry);
    }

    public void incrementCreated() { customersCreatedCounter.increment(); }
    public void incrementUpdated() { customersUpdatedCounter.increment(); }
    public void incrementOutboxPublished() { outboxPublishedCounter.increment(); }
    public void incrementOutboxFailed() { outboxFailedCounter.increment(); }
}
