package com.dgl.inventory.outbox;

import com.dgl.inventory.config.InventoryMetrics;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.apache.kafka.clients.producer.ProducerRecord;
import org.apache.kafka.common.header.internals.RecordHeader;
import org.springframework.data.domain.PageRequest;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;

import java.nio.charset.StandardCharsets;
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
    private final ObjectMapper objectMapper;
    private final InventoryMetrics inventoryMetrics;

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
                ProducerRecord<String, String> record = new ProducerRecord<>(topic, event.getAggregateId(), event.getPayload());

                try {
                    JsonNode root = objectMapper.readTree(event.getPayload());
                    if (root.hasNonNull("traceparent")) {
                        String traceparent = root.path("traceparent").asText();
                        record.headers().add(new RecordHeader("traceparent", traceparent.getBytes(StandardCharsets.UTF_8)));
                    }
                    if (root.hasNonNull("correlationId")) {
                        String correlationId = root.path("correlationId").asText();
                        record.headers().add(new RecordHeader("X-Correlation-Id", correlationId.getBytes(StandardCharsets.UTF_8)));
                    }
                    if (root.hasNonNull("causationId")) {
                        String causationId = root.path("causationId").asText();
                        record.headers().add(new RecordHeader("X-Causation-Id", causationId.getBytes(StandardCharsets.UTF_8)));
                    }
                } catch (Exception ex) {
                    log.warn("Failed to extract tracing headers from payload for event {}: {}", event.getId(), ex.getMessage());
                }

                kafkaTemplate.send(record);
                event.setStatus(OutboxStatus.PUBLISHED);
                event.setProcessedAt(Instant.now());
                inventoryMetrics.incrementOutboxPublished();
                log.debug("Published inventory outbox event id: {} to topic: {}", event.getId(), topic);
            } catch (Exception ex) {
                log.error("Failed to publish inventory outbox event id: {} to topic: {}. Reason: {}",
                        event.getId(), topic, ex.getMessage(), ex);
                event.setRetryCount(event.getRetryCount() + 1);
                event.setErrorMessage(ex.getMessage());
                inventoryMetrics.incrementOutboxFailed();
                if (event.getRetryCount() >= MAX_RETRIES) {
                    event.setStatus(OutboxStatus.FAILED);
                }
            }
        }
    }

    private String resolveTopic(String eventType) {
        return switch (eventType) {
            case "InventoryReserved" -> "inventory.reserved";
            case "InventoryReleased" -> "inventory.released";
            case "InventoryFailed" -> "inventory.failed";
            default -> "inventory.events";
        };
    }
}
