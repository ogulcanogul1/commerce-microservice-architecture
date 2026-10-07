package com.dgl.shipping.outbox;

import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.data.domain.PageRequest;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;

import java.time.Instant;
import java.util.List;

@Slf4j
@Component
@RequiredArgsConstructor
public class OutboxPoller {

    private static final int BATCH_SIZE = 50;
    private static final int MAX_RETRIES = 3;

    private final OutboxEventRepository outboxEventRepository;
    private final KafkaTemplate<String, String> kafkaTemplate;

    @Scheduled(fixedDelayString = "${outbox.poller.interval-ms:1000}")
    @Transactional
    public void pollAndPublish() {
        List<OutboxEvent> pendingEvents = outboxEventRepository.findByStatusOrderByCreatedAtAsc(
                OutboxStatus.PENDING, PageRequest.of(0, BATCH_SIZE));

        if (pendingEvents.isEmpty()) {
            return;
        }

        for (OutboxEvent event : pendingEvents) {
            String topic = resolveTopic(event.getType());
            try {
                kafkaTemplate.send(topic, event.getAggregateId(), event.getPayload());
                event.setStatus(OutboxStatus.PUBLISHED);
                event.setProcessedAt(Instant.now());
                log.debug("Published shipping outbox event id: {} to topic: {}", event.getId(), topic);
            } catch (Exception ex) {
                log.error("Failed to publish shipping outbox event id: {} to topic: {}. Reason: {}",
                        event.getId(), topic, ex.getMessage(), ex);
                event.setRetryCount(event.getRetryCount() + 1);
                event.setErrorMessage(ex.getMessage());
                if (event.getRetryCount() >= MAX_RETRIES) {
                    event.setStatus(OutboxStatus.FAILED);
                }
            }
        }
    }

    private String resolveTopic(String eventType) {
        return switch (eventType) {
            case "ShipmentCreated" -> "shipments.created";
            case "ShipmentDelivered" -> "shipments.delivered";
            case "ShipmentCancelled" -> "shipments.cancelled";
            default -> "shipments.events";
        };
    }
}
