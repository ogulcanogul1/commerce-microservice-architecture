package com.dgl.payment.config;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.stereotype.Component;

@Component
public class PaymentMetrics {

    private final Counter paymentsAuthorizedCounter;
    private final Counter paymentsCapturedCounter;
    private final Counter paymentsFailedCounter;
    private final Counter paymentsRefundedCounter;
    private final Counter duplicateEventsCounter;
    private final Counter outboxPublishedCounter;
    private final Counter outboxFailedCounter;

    public PaymentMetrics(MeterRegistry registry) {
        this.paymentsAuthorizedCounter = Counter.builder("payments.authorized.total")
                .description("Total number of payments successfully authorized")
                .register(registry);

        this.paymentsCapturedCounter = Counter.builder("payments.captured.total")
                .description("Total number of payments successfully captured")
                .register(registry);

        this.paymentsFailedCounter = Counter.builder("payments.failed.total")
                .description("Total number of failed payment attempts")
                .register(registry);

        this.paymentsRefundedCounter = Counter.builder("payments.refunded.total")
                .description("Total number of refunded payments")
                .register(registry);

        this.duplicateEventsCounter = Counter.builder("idempotent.duplicate.events.total")
                .tag("service", "payment-service")
                .description("Total number of duplicate Kafka events intercepted")
                .register(registry);

        this.outboxPublishedCounter = Counter.builder("outbox.events.published.total")
                .tag("service", "payment-service")
                .description("Total number of outbox events published to Kafka")
                .register(registry);

        this.outboxFailedCounter = Counter.builder("outbox.events.failed.total")
                .tag("service", "payment-service")
                .description("Total number of outbox event publish failures")
                .register(registry);
    }

    public void incrementAuthorized() { paymentsAuthorizedCounter.increment(); }
    public void incrementCaptured() { paymentsCapturedCounter.increment(); }
    public void incrementFailed() { paymentsFailedCounter.increment(); }
    public void incrementRefunded() { paymentsRefundedCounter.increment(); }
    public void incrementDuplicateEvents() { duplicateEventsCounter.increment(); }
    public void incrementOutboxPublished() { outboxPublishedCounter.increment(); }
    public void incrementOutboxFailed() { outboxFailedCounter.increment(); }
}
