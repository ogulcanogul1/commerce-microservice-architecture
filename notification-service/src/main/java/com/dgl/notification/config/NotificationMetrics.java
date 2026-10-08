package com.dgl.notification.config;

import com.dgl.notification.domain.NotificationChannel;
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.stereotype.Component;

import java.util.EnumMap;
import java.util.Map;

@Component
public class NotificationMetrics {

    private final Map<NotificationChannel, Counter> sentCounters = new EnumMap<>(NotificationChannel.class);
    private final Map<NotificationChannel, Counter> failedCounters = new EnumMap<>(NotificationChannel.class);
    private final Counter duplicateEventsCounter;
    private final MeterRegistry meterRegistry;

    public NotificationMetrics(MeterRegistry registry) {
        this.meterRegistry = registry;

        for (NotificationChannel channel : NotificationChannel.values()) {
            sentCounters.put(channel, Counter.builder("notifications.sent.total")
                    .tag("channel", channel.name())
                    .description("Total number of successfully sent notifications")
                    .register(registry));

            failedCounters.put(channel, Counter.builder("notifications.failed.total")
                    .tag("channel", channel.name())
                    .description("Total number of failed notification dispatches")
                    .register(registry));
        }

        this.duplicateEventsCounter = Counter.builder("idempotent.duplicate.events.total")
                .tag("service", "notification-service")
                .description("Total number of duplicate Kafka events intercepted")
                .register(registry);
    }

    public void incrementSent(NotificationChannel channel) {
        Counter counter = sentCounters.get(channel);
        if (counter != null) {
            counter.increment();
        }
    }

    public void incrementFailed(NotificationChannel channel) {
        Counter counter = failedCounters.get(channel);
        if (counter != null) {
            counter.increment();
        }
    }

    public void incrementDuplicateEvents() {
        duplicateEventsCounter.increment();
    }
}
