package com.dgl.order.messaging.consumer;

import com.dgl.order.domain.ProcessedEvent;
import com.dgl.order.domain.ProcessedEventId;
import com.dgl.order.repository.ProcessedEventRepository;
import com.dgl.order.service.OrderService;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;

import java.time.Instant;
import java.util.UUID;

@Slf4j
@Component
@RequiredArgsConstructor
public class InventoryEventListener {

    private static final String CONSUMER_GROUP = "order-service-group";

    private final OrderService orderService;
    private final ProcessedEventRepository processedEventRepository;
    private final ObjectMapper objectMapper;

    @KafkaListener(topics = "inventory.reserved", groupId = CONSUMER_GROUP)
    @Transactional
    public void handleInventoryReserved(String message) {
        try {
            JsonNode root = objectMapper.readTree(message);
            UUID eventId = UUID.fromString(root.path("eventId").asText());
            String eventType = root.path("eventType").asText();

            ProcessedEventId processedId = ProcessedEventId.builder()
                    .consumerGroup(CONSUMER_GROUP)
                    .eventId(eventId)
                    .build();

            if (processedEventRepository.existsById(processedId)) {
                log.info("Duplicate inventory reserved event ignored for eventId: {}", eventId);
                return;
            }

            JsonNode payload = root.path("payload");
            UUID orderId = UUID.fromString(payload.path("orderId").asText());

            orderService.handleInventoryReserved(orderId);
            log.info("Handled InventoryReserved event for orderId: {}", orderId);

            processedEventRepository.save(ProcessedEvent.builder()
                    .id(processedId)
                    .eventType(eventType)
                    .processedAt(Instant.now())
                    .build());

        } catch (Exception ex) {
            log.error("Failed to process inventory reserved event in order-service: {}", message, ex);
            throw new RuntimeException("Error processing InventoryReserved event in order-service", ex);
        }
    }

    @KafkaListener(topics = "inventory.failed", groupId = CONSUMER_GROUP)
    @Transactional
    public void handleInventoryFailed(String message) {
        try {
            JsonNode root = objectMapper.readTree(message);
            UUID eventId = UUID.fromString(root.path("eventId").asText());
            String eventType = root.path("eventType").asText();

            ProcessedEventId processedId = ProcessedEventId.builder()
                    .consumerGroup(CONSUMER_GROUP)
                    .eventId(eventId)
                    .build();

            if (processedEventRepository.existsById(processedId)) {
                log.info("Duplicate inventory failed event ignored for eventId: {}", eventId);
                return;
            }

            JsonNode payload = root.path("payload");
            UUID orderId = UUID.fromString(payload.path("orderId").asText());
            String reason = payload.hasNonNull("reason") ? payload.path("reason").asText() : "Insufficient inventory";

            orderService.handleInventoryFailed(orderId, reason);
            log.info("Handled InventoryFailed event for orderId: {}, reason: {}", orderId, reason);

            processedEventRepository.save(ProcessedEvent.builder()
                    .id(processedId)
                    .eventType(eventType)
                    .processedAt(Instant.now())
                    .build());

        } catch (Exception ex) {
            log.error("Failed to process inventory failed event in order-service: {}", message, ex);
            throw new RuntimeException("Error processing InventoryFailed event in order-service", ex);
        }
    }
}
