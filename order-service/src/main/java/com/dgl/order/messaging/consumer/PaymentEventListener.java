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
public class PaymentEventListener {

    private static final String CONSUMER_GROUP = "order-service-group";

    private final OrderService orderService;
    private final ProcessedEventRepository processedEventRepository;
    private final ObjectMapper objectMapper;

    @KafkaListener(topics = "payments.authorized", groupId = CONSUMER_GROUP)
    @Transactional
    public void handlePaymentAuthorized(String message) {
        try {
            JsonNode root = objectMapper.readTree(message);
            UUID eventId = UUID.fromString(root.path("eventId").asText());
            String eventType = root.path("eventType").asText();

            ProcessedEventId processedId = ProcessedEventId.builder()
                    .consumerGroup(CONSUMER_GROUP)
                    .eventId(eventId)
                    .build();

            if (processedEventRepository.existsById(processedId)) {
                log.info("Duplicate payment authorized event ignored for eventId: {}", eventId);
                return;
            }

            JsonNode payload = root.path("payload");
            UUID orderId = UUID.fromString(payload.path("orderId").asText());

            orderService.handlePaymentAuthorized(orderId);
            log.info("Handled PaymentAuthorized event for orderId: {}", orderId);

            processedEventRepository.save(ProcessedEvent.builder()
                    .id(processedId)
                    .eventType(eventType)
                    .processedAt(Instant.now())
                    .build());

        } catch (Exception ex) {
            log.error("Failed to process payment authorized event in order-service: {}", message, ex);
            throw new RuntimeException("Error processing PaymentAuthorized event in order-service", ex);
        }
    }

    @KafkaListener(topics = "payments.failed", groupId = CONSUMER_GROUP)
    @Transactional
    public void handlePaymentFailed(String message) {
        try {
            JsonNode root = objectMapper.readTree(message);
            UUID eventId = UUID.fromString(root.path("eventId").asText());
            String eventType = root.path("eventType").asText();

            ProcessedEventId processedId = ProcessedEventId.builder()
                    .consumerGroup(CONSUMER_GROUP)
                    .eventId(eventId)
                    .build();

            if (processedEventRepository.existsById(processedId)) {
                log.info("Duplicate payment failed event ignored for eventId: {}", eventId);
                return;
            }

            JsonNode payload = root.path("payload");
            UUID orderId = UUID.fromString(payload.path("orderId").asText());
            String reason = payload.hasNonNull("reason") ? payload.path("reason").asText() : "Payment rejected";

            orderService.handlePaymentFailed(orderId, reason);
            log.info("Handled PaymentFailed event for orderId: {}, reason: {}", orderId, reason);

            processedEventRepository.save(ProcessedEvent.builder()
                    .id(processedId)
                    .eventType(eventType)
                    .processedAt(Instant.now())
                    .build());

        } catch (Exception ex) {
            log.error("Failed to process payment failed event in order-service: {}", message, ex);
            throw new RuntimeException("Error processing PaymentFailed event in order-service", ex);
        }
    }
}
