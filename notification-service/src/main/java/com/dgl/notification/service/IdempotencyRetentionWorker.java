package com.dgl.notification.service;

import com.dgl.notification.repository.ProcessedEventRepository;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;

import java.time.Instant;
import java.time.temporal.ChronoUnit;

@Component
@RequiredArgsConstructor
@Slf4j
@ConditionalOnProperty(name = "idempotency.retention.enabled", havingValue = "true", matchIfMissing = true)
public class IdempotencyRetentionWorker {

    private final ProcessedEventRepository processedEventRepository;

    @Value("${idempotency.retention.days:7}")
    private int idempotencyRetentionDays;

    @Scheduled(cron = "${idempotency.retention.cron:0 0 3 * * ?}")
    @Transactional
    public void purgeExpiredProcessedEvents() {
        log.info("Starting notification idempotency retention cleanup task...");

        Instant cutoff = Instant.now().minus(idempotencyRetentionDays, ChronoUnit.DAYS);
        int deleted = processedEventRepository.deleteByProcessedAtBefore(cutoff);
        log.info("Purged {} processed event(s) older than {} days (cutoff: {})",
                deleted, idempotencyRetentionDays, cutoff);
    }
}
