package com.dgl.product.config;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.stereotype.Component;

@Component
public class ProductMetrics {

    private final Counter productsCreatedCounter;
    private final Counter productsUpdatedCounter;
    private final Counter productsDeletedCounter;
    private final Counter outboxPublishedCounter;
    private final Counter outboxFailedCounter;

    public ProductMetrics(MeterRegistry registry) {
        this.productsCreatedCounter = Counter.builder("products.created.total")
                .description("Total number of products created")
                .register(registry);

        this.productsUpdatedCounter = Counter.builder("products.updated.total")
                .description("Total number of products updated")
                .register(registry);

        this.productsDeletedCounter = Counter.builder("products.deleted.total")
                .description("Total number of products deleted or archived")
                .register(registry);

        this.outboxPublishedCounter = Counter.builder("outbox.events.published.total")
                .tag("service", "product-service")
                .description("Total number of outbox events published to Kafka")
                .register(registry);

        this.outboxFailedCounter = Counter.builder("outbox.events.failed.total")
                .tag("service", "product-service")
                .description("Total number of outbox event publish failures")
                .register(registry);
    }

    public void incrementCreated() { productsCreatedCounter.increment(); }
    public void incrementUpdated() { productsUpdatedCounter.increment(); }
    public void incrementDeleted() { productsDeletedCounter.increment(); }
    public void incrementOutboxPublished() { outboxPublishedCounter.increment(); }
    public void incrementOutboxFailed() { outboxFailedCounter.increment(); }
}
