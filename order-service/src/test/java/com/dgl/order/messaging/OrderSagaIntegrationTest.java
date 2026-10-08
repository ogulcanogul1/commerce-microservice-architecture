package com.dgl.order.messaging;

import com.dgl.order.domain.Order;
import com.dgl.order.domain.OrderSagaState;
import com.dgl.order.domain.OrderStatus;
import com.dgl.order.outbox.OutboxEventRepository;
import com.dgl.order.repository.OrderRepository;
import com.dgl.order.repository.ProcessedEventRepository;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.test.context.EmbeddedKafka;
import org.springframework.test.annotation.DirtiesContext;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.*;
import java.util.concurrent.TimeUnit;

import static org.assertj.core.api.Assertions.assertThat;
import static org.awaitility.Awaitility.await;

@SpringBootTest
@DirtiesContext
@EmbeddedKafka(
        partitions = 1,
        topics = {
                "inventory.reserved",
                "inventory.failed",
                "payments.authorized",
                "payments.failed",
                "shipments.created",
                "orders.confirmed",
                "orders.cancelled"
        }
)
class OrderSagaIntegrationTest {

    @Autowired
    private KafkaTemplate<String, String> kafkaTemplate;

    @Autowired
    private com.dgl.order.service.OrderService orderService;

    @Autowired
    private OrderRepository orderRepository;

    @Autowired
    private OutboxEventRepository outboxEventRepository;

    @Autowired
    private ProcessedEventRepository processedEventRepository;

    @Autowired
    private ObjectMapper objectMapper;

    @Test
    @DisplayName("Saga Happy Path: inventory.reserved + payments.authorized -> Order becomes CONFIRMED with outbox event")
    void sagaHappyPath_shouldConfirmOrder() throws Exception {
        com.dgl.order.dto.response.OrderResponse order = createTestOrder();
        UUID orderId = order.id();

        // 1. Send inventory.reserved event
        UUID invEventId = UUID.randomUUID();
        Map<String, Object> invEnvelope = Map.of(
                "eventId", invEventId.toString(),
                "eventType", "InventoryReserved",
                "aggregateId", orderId.toString(),
                "aggregateType", "Inventory",
                "timestamp", Instant.now().toString(),
                "version", 1,
                "correlationId", order.correlationId().toString(),
                "payload", Map.of("orderId", orderId.toString(), "items", List.of())
        );
        kafkaTemplate.send("inventory.reserved", objectMapper.writeValueAsString(invEnvelope));

        // 2. Send payments.authorized event
        UUID payEventId = UUID.randomUUID();
        Map<String, Object> payEnvelope = Map.of(
                "eventId", payEventId.toString(),
                "eventType", "PaymentAuthorized",
                "aggregateId", UUID.randomUUID().toString(),
                "aggregateType", "Payment",
                "timestamp", Instant.now().toString(),
                "version", 1,
                "correlationId", order.correlationId().toString(),
                "payload", Map.of(
                        "paymentId", UUID.randomUUID().toString(),
                        "orderId", orderId.toString(),
                        "customerId", order.customerId().toString(),
                        "amount", order.totalAmount(),
                        "currency", "TRY"
                )
        );
        kafkaTemplate.send("payments.authorized", objectMapper.writeValueAsString(payEnvelope));

        // 3. Await order confirmation and outbox record
        await().atMost(10, TimeUnit.SECONDS).untilAsserted(() -> {
            Order updated = orderRepository.findById(orderId).orElseThrow();
            assertThat(updated.getStatus()).isEqualTo(OrderStatus.CONFIRMED);
            assertThat(updated.getSagaState().getCurrentStep()).isEqualTo("CONFIRMED");
            assertThat(updated.getSagaState().getInventoryReservedAt()).isNotNull();
            assertThat(updated.getSagaState().getPaymentAuthorizedAt()).isNotNull();

            boolean confirmedOutboxExists = outboxEventRepository.findAll().stream()
                    .anyMatch(e -> "OrderConfirmed".equals(e.getType()) && orderId.toString().equals(e.getAggregateId()));
            assertThat(confirmedOutboxExists).isTrue();
        });
    }

    @Test
    @DisplayName("Saga Compensating Path: inventory.failed -> Order becomes CANCELLED with outbox event")
    void sagaCompensatingPath_inventoryFailed_shouldCancelOrder() throws Exception {
        com.dgl.order.dto.response.OrderResponse order = createTestOrder();
        UUID orderId = order.id();

        UUID failEventId = UUID.randomUUID();
        Map<String, Object> failEnvelope = Map.of(
                "eventId", failEventId.toString(),
                "eventType", "InventoryFailed",
                "aggregateId", orderId.toString(),
                "aggregateType", "Inventory",
                "timestamp", Instant.now().toString(),
                "version", 1,
                "correlationId", order.correlationId().toString(),
                "payload", Map.of(
                        "orderId", orderId.toString(),
                        "sku", "SKU-TEST-999",
                        "requestedQuantity", 2,
                        "availableQuantity", 0,
                        "reason", "Insufficient stock for SKU-TEST-999"
                )
        );
        kafkaTemplate.send("inventory.failed", objectMapper.writeValueAsString(failEnvelope));

        await().atMost(10, TimeUnit.SECONDS).untilAsserted(() -> {
            Order updated = orderRepository.findById(orderId).orElseThrow();
            assertThat(updated.getStatus()).isEqualTo(OrderStatus.CANCELLED);
            assertThat(updated.getSagaState().getCurrentStep()).isEqualTo("INVENTORY_FAILED");
            assertThat(updated.getFailureReason()).contains("Insufficient stock for SKU-TEST-999");

            boolean cancelledOutboxExists = outboxEventRepository.findAll().stream()
                    .anyMatch(e -> "OrderCancelled".equals(e.getType()) && orderId.toString().equals(e.getAggregateId()));
            assertThat(cancelledOutboxExists).isTrue();
        });
    }

    @Test
    @DisplayName("Idempotency: Duplicate Kafka event should be safely ignored")
    void idempotency_duplicateEventShouldBeIgnored() throws Exception {
        com.dgl.order.dto.response.OrderResponse order = createTestOrder();
        UUID orderId = order.id();

        UUID duplicateEventId = UUID.randomUUID();
        Map<String, Object> invEnvelope = Map.of(
                "eventId", duplicateEventId.toString(),
                "eventType", "InventoryReserved",
                "aggregateId", orderId.toString(),
                "aggregateType", "Inventory",
                "timestamp", Instant.now().toString(),
                "version", 1,
                "correlationId", order.correlationId().toString(),
                "payload", Map.of("orderId", orderId.toString(), "items", List.of())
        );

        String json = objectMapper.writeValueAsString(invEnvelope);

        // Send first time
        kafkaTemplate.send("inventory.reserved", json);

        await().atMost(10, TimeUnit.SECONDS).untilAsserted(() -> {
            Order updated = orderRepository.findById(orderId).orElseThrow();
            assertThat(updated.getStatus()).isEqualTo(OrderStatus.INVENTORY_RESERVED);
        });

        // Send second time with identical eventId
        kafkaTemplate.send("inventory.reserved", json);

        // Status should remain unchanged, no exceptions
        await().pollDelay(2, TimeUnit.SECONDS).atMost(5, TimeUnit.SECONDS).untilAsserted(() -> {
            Order updated = orderRepository.findById(orderId).orElseThrow();
            assertThat(updated.getStatus()).isEqualTo(OrderStatus.INVENTORY_RESERVED);
        });
    }

    private com.dgl.order.dto.response.OrderResponse createTestOrder() {
        com.dgl.order.dto.request.CreateOrderRequest request = new com.dgl.order.dto.request.CreateOrderRequest(
                UUID.randomUUID(),
                List.of(new com.dgl.order.dto.request.CreateOrderItemRequest("SKU-TEST-1", "Test Product", new BigDecimal("150.00"), 1)),
                "{\"city\":\"Istanbul\",\"address\":\"Bagdat Cad. No:1\"}",
                "TRY"
        );

        return orderService.createOrder(request, UUID.randomUUID());
    }
}
