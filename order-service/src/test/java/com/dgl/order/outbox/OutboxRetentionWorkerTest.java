package com.dgl.order.outbox;

import com.dgl.order.repository.ProcessedEventRepository;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.test.util.ReflectionTestUtils;

import java.time.Instant;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.*;

@ExtendWith(MockitoExtension.class)
class OutboxRetentionWorkerTest {

    @Mock
    private OutboxEventRepository outboxEventRepository;

    @Mock
    private ProcessedEventRepository processedEventRepository;

    @InjectMocks
    private OutboxRetentionWorker retentionWorker;

    @BeforeEach
    void setUp() {
        ReflectionTestUtils.setField(retentionWorker, "outboxRetentionDays", 7);
        ReflectionTestUtils.setField(retentionWorker, "idempotencyRetentionDays", 7);
    }

    @Test
    @DisplayName("Should purge published outbox and processed events older than 7 days")
    void shouldPurgeExpiredEvents() {
        when(outboxEventRepository.deleteByStatusAndCreatedAtBefore(eq(OutboxStatus.PUBLISHED), any(Instant.class)))
                .thenReturn(5);
        when(processedEventRepository.deleteByProcessedAtBefore(any(Instant.class)))
                .thenReturn(12);

        retentionWorker.purgeExpiredEvents();

        verify(outboxEventRepository).deleteByStatusAndCreatedAtBefore(eq(OutboxStatus.PUBLISHED), any(Instant.class));
        verify(processedEventRepository).deleteByProcessedAtBefore(any(Instant.class));
    }
}
