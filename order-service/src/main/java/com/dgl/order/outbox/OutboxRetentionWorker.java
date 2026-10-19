package com.dgl.order.outbox;

import com.dgl.order.lock.DistributedLockService;
import com.dgl.order.repository.ProcessedEventRepository;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;

import java.time.Duration;
import java.time.Instant;
import java.time.temporal.ChronoUnit;

@Component
@RequiredArgsConstructor
@Slf4j
@ConditionalOnProperty(name = "outbox.retention.enabled", havingValue = "true", matchIfMissing = true)
public class OutboxRetentionWorker {

    public static final String LOCK_KEY = "lock:order-service:retention-cleanup";
    public static final Duration LOCK_LEASE_TIME = Duration.ofMinutes(15);

    private final OutboxEventRepository outboxEventRepository;
    private final ProcessedEventRepository processedEventRepository;
    private final DistributedLockService lockService;

    @Value("${outbox.retention.days:7}")
    private int outboxRetentionDays;

    @Value("${idempotency.retention.days:7}")
    private int idempotencyRetentionDays;

    @Scheduled(cron = "${outbox.retention.cron:0 0 3 * * ?}")
    public void purgeExpiredEvents() {
        lockService.executeWithLock(LOCK_KEY, LOCK_LEASE_TIME, this::executePurge);
    }

    @Transactional
    public void executePurge() {
        log.info("Starting outbox and idempotency retention cleanup task under distributed lock...");

        Instant outboxCutoff = Instant.now().minus(outboxRetentionDays, ChronoUnit.DAYS);
        int deletedOutbox = outboxEventRepository.deleteByStatusAndCreatedAtBefore(OutboxStatus.PUBLISHED, outboxCutoff);
        log.info("Purged {} published outbox event(s) older than {} days (cutoff: {})",
                deletedOutbox, outboxRetentionDays, outboxCutoff);

        Instant idempotencyCutoff = Instant.now().minus(idempotencyRetentionDays, ChronoUnit.DAYS);
        int deletedProcessed = processedEventRepository.deleteByProcessedAtBefore(idempotencyCutoff);
        log.info("Purged {} processed event(s) older than {} days (cutoff: {})",
                deletedProcessed, idempotencyRetentionDays, idempotencyCutoff);
    }
}
