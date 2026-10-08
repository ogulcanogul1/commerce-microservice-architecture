package com.dgl.shipping.messaging;

import com.dgl.shipping.domain.Shipment;
import com.dgl.shipping.domain.ShipmentStatus;
import com.dgl.shipping.outbox.OutboxEventRepository;
import com.dgl.shipping.repository.ProcessedEventRepository;
import com.dgl.shipping.repository.ShipmentRepository;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.test.context.EmbeddedKafka;
import org.springframework.test.annotation.DirtiesContext;

import java.time.Instant;
import java.util.Map;
import java.util.Optional;
import java.util.UUID;
import java.util.concurrent.TimeUnit;

import static org.assertj.core.api.Assertions.assertThat;
import static org.awaitility.Awaitility.await;

@SpringBootTest
@DirtiesContext
@EmbeddedKafka(
        partitions = 1,
        topics = {
                "orders.confirmed",
                "orders.cancelled"
        }
)
class OrderEventListenerIntegrationTest {

    @Autowired
    private KafkaTemplate<String, String> kafkaTemplate;

    @Autowired
    private ShipmentRepository shipmentRepository;

    @Autowired
    private OutboxEventRepository outboxEventRepository;

    @Autowired
    private ProcessedEventRepository processedEventRepository;

    @Autowired
    private ObjectMapper objectMapper;

    @Test
    @DisplayName("orders.confirmed: Should initiate shipment and emit ShipmentCreated outbox event")
    void handleOrderConfirmed_shouldCreateShipmentAndEmitOutboxEvent() throws Exception {
        UUID orderId = UUID.randomUUID();
        UUID customerId = UUID.randomUUID();
        UUID eventId = UUID.randomUUID();

        Map<String, Object> event = Map.of(
                "eventId", eventId.toString(),
                "eventType", "OrderConfirmed",
                "aggregateId", orderId.toString(),
                "aggregateType", "Order",
                "timestamp", Instant.now().toString(),
                "version", 1,
                "correlationId", UUID.randomUUID().toString(),
                "payload", Map.of(
                        "orderId", orderId.toString(),
                        "orderNumber", "ORD-TEST-1234",
                        "customerId", customerId.toString(),
                        "shippingAddress", "{\"address\": \"Bagdat Cad. No:1 Kadikoy Istanbul\"}",
                        "totalAmount", "300.00"
                )
        );

        kafkaTemplate.send("orders.confirmed", objectMapper.writeValueAsString(event));

        await().atMost(10, TimeUnit.SECONDS).untilAsserted(() -> {
            Optional<Shipment> shipmentOpt = shipmentRepository.findByOrderId(orderId);
            assertThat(shipmentOpt).isPresent();
            Shipment shipment = shipmentOpt.get();
            assertThat(shipment.getStatus()).isEqualTo(ShipmentStatus.CREATED);
            assertThat(shipment.getTrackingNumber()).startsWith("TRK-");

            boolean outboxCreatedExists = outboxEventRepository.findAll().stream()
                    .anyMatch(e -> "ShipmentCreated".equals(e.getType()) && shipment.getId().toString().equals(e.getAggregateId()));
            assertThat(outboxCreatedExists).isTrue();
        });
    }

    @Test
    @DisplayName("Idempotency: Duplicate orders.confirmed event should be ignored")
    void handleOrderConfirmed_duplicateEvent_shouldBeIgnored() throws Exception {
        UUID orderId = UUID.randomUUID();
        UUID customerId = UUID.randomUUID();
        UUID eventId = UUID.randomUUID();

        Map<String, Object> event = Map.of(
                "eventId", eventId.toString(),
                "eventType", "OrderConfirmed",
                "aggregateId", orderId.toString(),
                "aggregateType", "Order",
                "timestamp", Instant.now().toString(),
                "version", 1,
                "correlationId", UUID.randomUUID().toString(),
                "payload", Map.of(
                        "orderId", orderId.toString(),
                        "orderNumber", "ORD-TEST-5678",
                        "customerId", customerId.toString(),
                        "shippingAddress", "{\"address\": \"Kadikoy Istanbul\"}",
                        "totalAmount", "100.00"
                )
        );

        String json = objectMapper.writeValueAsString(event);

        // Send first time
        kafkaTemplate.send("orders.confirmed", json);

        await().atMost(10, TimeUnit.SECONDS).untilAsserted(() -> {
            assertThat(shipmentRepository.findByOrderId(orderId)).isPresent();
        });

        // Send second time with identical eventId
        kafkaTemplate.send("orders.confirmed", json);

        await().pollDelay(2, TimeUnit.SECONDS).atMost(5, TimeUnit.SECONDS).untilAsserted(() -> {
            assertThat(shipmentRepository.findByOrderId(orderId)).isPresent();
        });
    }

    @Test
    @DisplayName("orders.cancelled: Should cancel active shipment and emit ShipmentCancelled outbox event")
    void handleOrderCancelled_shouldCancelShipment() throws Exception {
        UUID orderId = UUID.randomUUID();
        UUID customerId = UUID.randomUUID();
        UUID confirmEventId = UUID.randomUUID();

        // 1. Create shipment via orders.confirmed
        Map<String, Object> confirmEvent = Map.of(
                "eventId", confirmEventId.toString(),
                "eventType", "OrderConfirmed",
                "aggregateId", orderId.toString(),
                "aggregateType", "Order",
                "timestamp", Instant.now().toString(),
                "version", 1,
                "correlationId", UUID.randomUUID().toString(),
                "payload", Map.of(
                        "orderId", orderId.toString(),
                        "orderNumber", "ORD-CANCEL-TEST",
                        "customerId", customerId.toString(),
                        "shippingAddress", "{\"address\": \"Besiktas Istanbul\"}",
                        "totalAmount", "150.00"
                )
        );
        kafkaTemplate.send("orders.confirmed", objectMapper.writeValueAsString(confirmEvent));

        await().atMost(10, TimeUnit.SECONDS).untilAsserted(() -> {
            assertThat(shipmentRepository.findByOrderId(orderId)).isPresent();
        });

        Shipment shipment = shipmentRepository.findByOrderId(orderId).orElseThrow();

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
                        "reason", "Order compensation cancelled"
                )
        );
        kafkaTemplate.send("orders.cancelled", objectMapper.writeValueAsString(cancelEvent));

        // 3. Await cancellation and outbox event
        await().atMost(10, TimeUnit.SECONDS).untilAsserted(() -> {
            Shipment updated = shipmentRepository.findById(shipment.getId()).orElseThrow();
            assertThat(updated.getStatus()).isEqualTo(ShipmentStatus.CANCELLED);

            boolean outboxCancelExists = outboxEventRepository.findAll().stream()
                    .anyMatch(e -> "ShipmentCancelled".equals(e.getType()) && shipment.getId().toString().equals(e.getAggregateId()));
            assertThat(outboxCancelExists).isTrue();
        });
    }
}
