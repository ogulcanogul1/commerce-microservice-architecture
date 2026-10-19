package com.dgl.order.config;

import com.dgl.order.domain.DeadLetterStatus;
import com.dgl.order.repository.DeadLetterMessageRepository;
import io.micrometer.core.instrument.Gauge;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class DeadLetterMetricsConfigTest {

    @Mock
    private DeadLetterMessageRepository repository;

    @Test
    @DisplayName("Should expose dlt.messages.pending gauge reflecting repository count")
    void shouldExposePendingDeadLetterGauge() {
        MeterRegistry meterRegistry = new SimpleMeterRegistry();

        when(repository.countByStatus(DeadLetterStatus.PENDING)).thenReturn(4L);

        new DeadLetterMetricsConfig(meterRegistry, repository);

        Gauge gauge = meterRegistry.find("dlt.messages.pending").gauge();
        assertThat(gauge).isNotNull();
        assertThat(gauge.value()).isEqualTo(4.0);

        // When pending messages are resolved/replayed, gauge should update
        when(repository.countByStatus(DeadLetterStatus.PENDING)).thenReturn(0L);
        assertThat(gauge.value()).isEqualTo(0.0);
    }
}
