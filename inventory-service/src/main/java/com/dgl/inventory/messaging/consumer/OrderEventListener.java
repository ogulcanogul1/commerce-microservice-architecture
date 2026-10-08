package com.dgl.inventory.messaging.consumer;

import com.dgl.inventory.domain.ProcessedEvent;
import com.dgl.inventory.domain.ProcessedEventId;
import com.dgl.inventory.dto.request.ReserveStockItem;
import com.dgl.inventory.dto.request.ReserveStockRequest;
import com.dgl.inventory.exception.InsufficientStockException;
import com.dgl.inventory.exception.InventoryNotFoundException;
import com.dgl.inventory.messaging.event.InventoryFailedPayload;
import com.dgl.inventory.outbox.OutboxService;
import com.dgl.inventory.repository.ProcessedEventRepository;
import com.dgl.inventory.service.InventoryService;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;

import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;

@Slf4j
@Component
@RequiredArgsConstructor
public class OrderEventListener {

    private static final String CONSUMER_GROUP = "inventory-service-group";

    private final InventoryService inventoryService;
    private final OutboxService outboxService;
    private final ProcessedEventRepository processedEventRepository;
    private final ObjectMapper objectMapper;

    @KafkaListener(topics = "orders.created", groupId = CONSUMER_GROUP)
    @Transactional
    public void handleOrderCreated(String message) {
        try {
            JsonNode root = objectMapper.readTree(message);
            UUID eventId = UUID.fromString(root.path("eventId").asText());
            String eventType = root.path("eventType").asText();

            ProcessedEventId processedId = ProcessedEventId.builder()
                    .consumerGroup(CONSUMER_GROUP)
                    .eventId(eventId)
                    .build();

            if (processedEventRepository.existsById(processedId)) {
                log.info("Duplicate event ignored for eventId: {}", eventId);
                return;
            }

            UUID correlationId = root.hasNonNull("correlationId")
                    ? UUID.fromString(root.path("correlationId").asText())
                    : UUID.randomUUID();

            JsonNode payload = root.path("payload");
            UUID orderId = UUID.fromString(payload.path("orderId").asText());

            List<ReserveStockItem> items = new ArrayList<>();
            JsonNode itemsNode = payload.path("items");
            if (itemsNode.isArray()) {
                for (JsonNode item : itemsNode) {
                    items.add(new ReserveStockItem(
                            item.path("sku").asText(),
                            item.path("quantity").asInt()
                    ));
                }
            }

            try {
                inventoryService.reserveStock(new ReserveStockRequest(orderId, items, 15L));
                log.info("Stock reserved successfully for orderId: {}", orderId);
            } catch (InsufficientStockException ex) {
                log.warn("Insufficient stock for orderId: {}. Reason: {}", orderId, ex.getMessage());
                outboxService.recordEvent(
                        "Inventory",
                        orderId.toString(),
                        "InventoryFailed",
                        correlationId,
                        eventId,
                        new InventoryFailedPayload(
                                orderId,
                                ex.getSku(),
                                ex.getRequested(),
                                ex.getAvailable(),
                                ex.getMessage()
                        )
                );
            } catch (InventoryNotFoundException ex) {
                log.warn("Inventory item not found for orderId: {}. Reason: {}", orderId, ex.getMessage());
                outboxService.recordEvent(
                        "Inventory",
                        orderId.toString(),
                        "InventoryFailed",
                        correlationId,
                        eventId,
                        new InventoryFailedPayload(
                                orderId,
                                null,
                                0,
                                0,
                                ex.getMessage()
                        )
                );
            }

            processedEventRepository.save(ProcessedEvent.builder()
                    .id(processedId)
                    .eventType(eventType)
                    .processedAt(Instant.now())
                    .build());

        } catch (Exception ex) {
            log.error("Failed to process order created message: {}", message, ex);
            throw new RuntimeException("Error processing OrderCreated event", ex);
        }
    }

    @KafkaListener(topics = "orders.cancelled", groupId = CONSUMER_GROUP)
    @Transactional
    public void handleOrderCancelled(String message) {
        try {
            JsonNode root = objectMapper.readTree(message);
            UUID eventId = UUID.fromString(root.path("eventId").asText());
            String eventType = root.path("eventType").asText();

            ProcessedEventId processedId = ProcessedEventId.builder()
                    .consumerGroup(CONSUMER_GROUP)
                    .eventId(eventId)
                    .build();

            if (processedEventRepository.existsById(processedId)) {
                log.info("Duplicate cancellation event ignored for eventId: {}", eventId);
                return;
            }

            JsonNode payload = root.path("payload");
            UUID orderId = UUID.fromString(payload.path("orderId").asText());

            inventoryService.releaseStock(orderId);
            log.info("Stock reservation released for cancelled orderId: {}", orderId);

            processedEventRepository.save(ProcessedEvent.builder()
                    .id(processedId)
                    .eventType(eventType)
                    .processedAt(Instant.now())
                    .build());

        } catch (Exception ex) {
            log.error("Failed to process order cancelled message: {}", message, ex);
            throw new RuntimeException("Error processing OrderCancelled event", ex);
        }
    }
}
