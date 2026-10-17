package com.dgl.customer.outbox;

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
@ConditionalOnProperty(name = "outbox.retention.enabled", havingValue = "true", matchIfMissing = true)
public class OutboxRetentionWorker {

    private final OutboxEventRepository outboxEventRepository;

    @Value("${outbox.retention.days:7}")
    private int outboxRetentionDays;

    @Scheduled(cron = "${outbox.retention.cron:0 0 3 * * ?}")
    @Transactional
    public void purgeExpiredEvents() {
        log.info("Starting customer outbox retention cleanup task...");

        Instant outboxCutoff = Instant.now().minus(outboxRetentionDays, ChronoUnit.DAYS);
        int deletedOutbox = outboxEventRepository.deleteByStatusAndCreatedAtBefore(OutboxStatus.PUBLISHED, outboxCutoff);
        log.info("Purged {} published outbox event(s) older than {} days (cutoff: {})",
                deletedOutbox, outboxRetentionDays, outboxCutoff);
    }
}
