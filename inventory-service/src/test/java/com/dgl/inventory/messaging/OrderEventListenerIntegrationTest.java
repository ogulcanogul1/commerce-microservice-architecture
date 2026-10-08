package com.dgl.inventory.messaging;

import com.dgl.inventory.domain.InventoryItem;
import com.dgl.inventory.domain.ReservationStatus;
import com.dgl.inventory.domain.StockReservation;
import com.dgl.inventory.outbox.OutboxEventRepository;
import com.dgl.inventory.repository.InventoryItemRepository;
import com.dgl.inventory.repository.ProcessedEventRepository;
import com.dgl.inventory.repository.StockReservationRepository;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.test.context.EmbeddedKafka;
import org.springframework.test.annotation.DirtiesContext;

import java.time.Instant;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.TimeUnit;

import static org.assertj.core.api.Assertions.assertThat;
import static org.awaitility.Awaitility.await;

@SpringBootTest
@DirtiesContext
@EmbeddedKafka(
        partitions = 1,
        topics = {
                "orders.created",
                "orders.cancelled"
        }
)
class OrderEventListenerIntegrationTest {

    @Autowired
    private KafkaTemplate<String, String> kafkaTemplate;

    @Autowired
    private InventoryItemRepository inventoryItemRepository;

    @Autowired
    private StockReservationRepository stockReservationRepository;

    @Autowired
    private OutboxEventRepository outboxEventRepository;

    @Autowired
    private ProcessedEventRepository processedEventRepository;

    @Autowired
    private ObjectMapper objectMapper;

    private static final String SKU = "SKU-KAFKA-TEST";

    @BeforeEach
    void setUp() {
        if (inventoryItemRepository.findBySku(SKU).isEmpty()) {
            InventoryItem item = InventoryItem.builder()
                    .sku(SKU)
                    .totalQuantity(100)
                    .reservedQuantity(0)
                    .build();
            inventoryItemRepository.save(item);
        }
    }

    @Test
    @DisplayName("orders.created: Sufficient stock should reserve quantity and write InventoryReserved outbox event")
    void handleOrderCreated_sufficientStock_shouldReserveStock() throws Exception {
        UUID orderId = UUID.randomUUID();
        UUID eventId = UUID.randomUUID();

        Map<String, Object> event = Map.of(
                "eventId", eventId.toString(),
                "eventType", "OrderCreated",
                "aggregateId", orderId.toString(),
                "aggregateType", "Order",
                "timestamp", Instant.now().toString(),
                "version", 1,
                "correlationId", UUID.randomUUID().toString(),
                "payload", Map.of(
                        "orderId", orderId.toString(),
                        "items", List.of(Map.of("sku", SKU, "quantity", 10))
                )
        );

        kafkaTemplate.send("orders.created", objectMapper.writeValueAsString(event));

        await().atMost(10, TimeUnit.SECONDS).untilAsserted(() -> {
            List<StockReservation> reservations = stockReservationRepository.findByOrderId(orderId);
            assertThat(reservations).hasSize(1);
            assertThat(reservations.get(0).getStatus()).isEqualTo(ReservationStatus.RESERVED);
            assertThat(reservations.get(0).getQuantity()).isEqualTo(10);

            boolean outboxReservedExists = outboxEventRepository.findAll().stream()
                    .anyMatch(e -> "InventoryReserved".equals(e.getType()) && orderId.toString().equals(e.getAggregateId()));
            assertThat(outboxReservedExists).isTrue();
        });
    }

    @Test
    @DisplayName("orders.created: Insufficient stock should write InventoryFailed outbox event")
    void handleOrderCreated_insufficientStock_shouldEmitInventoryFailed() throws Exception {
        UUID orderId = UUID.randomUUID();
        UUID eventId = UUID.randomUUID();

        Map<String, Object> event = Map.of(
                "eventId", eventId.toString(),
                "eventType", "OrderCreated",
                "aggregateId", orderId.toString(),
                "aggregateType", "Order",
                "timestamp", Instant.now().toString(),
                "version", 1,
                "correlationId", UUID.randomUUID().toString(),
                "payload", Map.of(
                        "orderId", orderId.toString(),
                        "items", List.of(Map.of("sku", SKU, "quantity", 999)) // Exceeds available 100
                )
        );

        kafkaTemplate.send("orders.created", objectMapper.writeValueAsString(event));

        await().atMost(10, TimeUnit.SECONDS).untilAsserted(() -> {
            boolean outboxFailedExists = outboxEventRepository.findAll().stream()
                    .anyMatch(e -> "InventoryFailed".equals(e.getType()) && orderId.toString().equals(e.getAggregateId()));
            assertThat(outboxFailedExists).isTrue();
        });
    }

    @Test
    @DisplayName("Idempotency: Duplicate orders.created event should be processed only once")
    void handleOrderCreated_duplicateEvent_shouldBeIgnored() throws Exception {
        UUID orderId = UUID.randomUUID();
        UUID eventId = UUID.randomUUID();

        Map<String, Object> event = Map.of(
                "eventId", eventId.toString(),
                "eventType", "OrderCreated",
                "aggregateId", orderId.toString(),
                "aggregateType", "Order",
                "timestamp", Instant.now().toString(),
                "version", 1,
                "correlationId", UUID.randomUUID().toString(),
                "payload", Map.of(
                        "orderId", orderId.toString(),
                        "items", List.of(Map.of("sku", SKU, "quantity", 5))
                )
        );

        String json = objectMapper.writeValueAsString(event);

        // Send first time
        kafkaTemplate.send("orders.created", json);

        await().atMost(10, TimeUnit.SECONDS).untilAsserted(() -> {
            List<StockReservation> reservations = stockReservationRepository.findByOrderId(orderId);
            assertThat(reservations).hasSize(1);
        });

        // Send second time with identical eventId
        kafkaTemplate.send("orders.created", json);

        // Reservations should still be exactly 1
        await().pollDelay(2, TimeUnit.SECONDS).atMost(5, TimeUnit.SECONDS).untilAsserted(() -> {
            List<StockReservation> reservations = stockReservationRepository.findByOrderId(orderId);
            assertThat(reservations).hasSize(1);
        });
    }

    @Test
    @DisplayName("orders.cancelled: Should release existing reservations and emit InventoryReleased outbox event")
    void handleOrderCancelled_shouldReleaseStock() throws Exception {
        UUID orderId = UUID.randomUUID();
        UUID createEventId = UUID.randomUUID();

        // 1. Create reservation first
        Map<String, Object> createEvent = Map.of(
                "eventId", createEventId.toString(),
                "eventType", "OrderCreated",
                "aggregateId", orderId.toString(),
                "aggregateType", "Order",
                "timestamp", Instant.now().toString(),
                "version", 1,
                "correlationId", UUID.randomUUID().toString(),
                "payload", Map.of(
                        "orderId", orderId.toString(),
                        "items", List.of(Map.of("sku", SKU, "quantity", 8))
                )
        );
        kafkaTemplate.send("orders.created", objectMapper.writeValueAsString(createEvent));

        await().atMost(10, TimeUnit.SECONDS).untilAsserted(() -> {
            List<StockReservation> reservations = stockReservationRepository.findByOrderId(orderId);
            assertThat(reservations).hasSize(1);
        });

        // 2. Send orders.cancelled event
        UUID cancelEventId = UUID.randomUUID();
        Map<String, Object> cancelEvent = Map.of(
                "eventId", cancelEventId.toString(),
                "eventType", "OrderCancelled",
                "aggregateId", orderId.toString(),
                "aggregateType", "Order",
                "timestamp", Instant.now().toString(),
                "version", 1,
                "correlationId", UUID.randomUUID().toString(),
                "payload", Map.of(
                        "orderId", orderId.toString(),
                        "reason", "Customer cancelled"
                )
        );
        kafkaTemplate.send("orders.cancelled", objectMapper.writeValueAsString(cancelEvent));

        // 3. Verify reservation is RELEASED and outbox contains InventoryReleased
        await().atMost(10, TimeUnit.SECONDS).untilAsserted(() -> {
            List<StockReservation> reservations = stockReservationRepository.findByOrderId(orderId);
            assertThat(reservations.get(0).getStatus()).isEqualTo(ReservationStatus.RELEASED);

            boolean outboxReleasedExists = outboxEventRepository.findAll().stream()
                    .anyMatch(e -> "InventoryReleased".equals(e.getType()) && orderId.toString().equals(e.getAggregateId()));
            assertThat(outboxReleasedExists).isTrue();
        });
    }
}
