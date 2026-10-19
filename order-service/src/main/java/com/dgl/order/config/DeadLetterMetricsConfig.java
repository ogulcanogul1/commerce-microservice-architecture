package com.dgl.order.config;

import com.dgl.order.domain.DeadLetterStatus;
import com.dgl.order.repository.DeadLetterMessageRepository;
import io.micrometer.core.instrument.Gauge;
import io.micrometer.core.instrument.MeterRegistry;
import lombok.extern.slf4j.Slf4j;
import org.springframework.context.annotation.Configuration;

/**
 * Exposes a real-time Micrometer Gauge metric ('dlt.messages.pending')
 * that Prometheus scrapes to trigger alerts when unresolved poison pill
 * messages reside in the Dead Letter Queue.
 */
@Slf4j
@Configuration
public class DeadLetterMetricsConfig {

    public DeadLetterMetricsConfig(MeterRegistry meterRegistry, DeadLetterMessageRepository repository) {
        Gauge.builder("dlt.messages.pending", repository, repo -> repo.countByStatus(DeadLetterStatus.PENDING))
                .description("Number of unresolved Dead Letter Queue messages awaiting operator inspection or redrive")
                .tag("service", "order-service")
                .register(meterRegistry);

        log.info("Registered Prometheus Micrometer Gauge for 'dlt.messages.pending'");
    }
}
