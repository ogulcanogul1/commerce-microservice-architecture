package com.dgl.order.config;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import org.springframework.stereotype.Component;

import java.util.concurrent.TimeUnit;

@Component
public class OrderMetrics {

    private final Counter ordersCreatedCounter;
    private final Counter ordersConfirmedCounter;
    private final Counter ordersCancelledCounter;
    private final Counter duplicateEventsCounter;
    private final Counter outboxPublishedCounter;
    private final Counter outboxFailedCounter;
    private final Counter sagaTimeoutsCounter;
    private final Timer sagaDurationTimer;

    public OrderMetrics(MeterRegistry registry) {
        this.ordersCreatedCounter = Counter.builder("orders.created.total")
                .description("Total number of orders created")
                .register(registry);

        this.ordersConfirmedCounter = Counter.builder("orders.confirmed.total")
                .description("Total number of orders successfully confirmed")
                .register(registry);

        this.ordersCancelledCounter = Counter.builder("orders.cancelled.total")
                .description("Total number of orders cancelled")
                .register(registry);

        this.duplicateEventsCounter = Counter.builder("idempotent.duplicate.events.total")
                .tag("service", "order-service")
                .description("Total number of duplicate Kafka events intercepted")
                .register(registry);

        this.outboxPublishedCounter = Counter.builder("outbox.events.published.total")
                .tag("service", "order-service")
                .description("Total number of outbox events published to Kafka")
                .register(registry);

        this.outboxFailedCounter = Counter.builder("outbox.events.failed.total")
                .tag("service", "order-service")
                .description("Total number of outbox event publish failures")
                .register(registry);

        this.sagaTimeoutsCounter = Counter.builder("order.saga.timeouts.total")
                .tag("service", "order-service")
                .description("Total number of orders timed out during Saga execution")
                .register(registry);

        this.sagaDurationTimer = Timer.builder("order.saga.duration")
                .description("Execution duration of the entire order Saga workflow")
                .register(registry);
    }

    public void incrementOrdersCreated() { ordersCreatedCounter.increment(); }
    public void incrementOrdersConfirmed() { ordersConfirmedCounter.increment(); }
    public void incrementOrdersCancelled() { ordersCancelledCounter.increment(); }
    public void incrementDuplicateEvents() { duplicateEventsCounter.increment(); }
    public void incrementOutboxPublished() { outboxPublishedCounter.increment(); }
    public void incrementOutboxFailed() { outboxFailedCounter.increment(); }
    public void incrementSagaTimeouts() { sagaTimeoutsCounter.increment(); }
    public void recordSagaDuration(long durationMs) { sagaDurationTimer.record(durationMs, TimeUnit.MILLISECONDS); }
}
