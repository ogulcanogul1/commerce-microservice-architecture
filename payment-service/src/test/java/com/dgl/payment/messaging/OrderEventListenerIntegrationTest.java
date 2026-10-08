package com.dgl.payment.messaging;

import com.dgl.payment.domain.Payment;
import com.dgl.payment.domain.PaymentStatus;
import com.dgl.payment.outbox.OutboxEventRepository;
import com.dgl.payment.repository.PaymentRepository;
import com.dgl.payment.repository.ProcessedEventRepository;
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
                "orders.created",
                "orders.cancelled"
        }
)
class OrderEventListenerIntegrationTest {

    @Autowired
    private KafkaTemplate<String, String> kafkaTemplate;

    @Autowired
    private PaymentRepository paymentRepository;

    @Autowired
    private OutboxEventRepository outboxEventRepository;

    @Autowired
    private ProcessedEventRepository processedEventRepository;

    @Autowired
    private ObjectMapper objectMapper;

    @Test
    @DisplayName("orders.created: Should authorize payment and write PaymentAuthorized outbox event")
    void handleOrderCreated_shouldAuthorizePaymentAndEmitOutboxEvent() throws Exception {
        UUID orderId = UUID.randomUUID();
        UUID customerId = UUID.randomUUID();
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
                        "customerId", customerId.toString(),
                        "totalAmount", "250.00",
                        "currency", "TRY"
                )
        );

        kafkaTemplate.send("orders.created", objectMapper.writeValueAsString(event));

        await().atMost(10, TimeUnit.SECONDS).untilAsserted(() -> {
            Optional<Payment> paymentOpt = paymentRepository.findByOrderId(orderId);
            assertThat(paymentOpt).isPresent();
            Payment payment = paymentOpt.get();
            assertThat(payment.getStatus()).isEqualTo(PaymentStatus.AUTHORIZED);
            assertThat(payment.getAmount()).isEqualByComparingTo(new BigDecimal("250.00"));

            boolean outboxAuthorizedExists = outboxEventRepository.findAll().stream()
                    .anyMatch(e -> "PaymentAuthorized".equals(e.getType()) && payment.getId().toString().equals(e.getAggregateId()));
            assertThat(outboxAuthorizedExists).isTrue();
        });
    }

    @Test
    @DisplayName("Idempotency: Duplicate orders.created event should be processed only once")
    void handleOrderCreated_duplicateEvent_shouldBeIgnored() throws Exception {
        UUID orderId = UUID.randomUUID();
        UUID customerId = UUID.randomUUID();
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
                        "customerId", customerId.toString(),
                        "totalAmount", "100.00",
                        "currency", "TRY"
                )
        );

        String json = objectMapper.writeValueAsString(event);

        // Send first time
        kafkaTemplate.send("orders.created", json);

        await().atMost(10, TimeUnit.SECONDS).untilAsserted(() -> {
            assertThat(paymentRepository.findByOrderId(orderId)).isPresent();
        });

        // Send second time with identical eventId
        kafkaTemplate.send("orders.created", json);

        await().pollDelay(2, TimeUnit.SECONDS).atMost(5, TimeUnit.SECONDS).untilAsserted(() -> {
            // Exactly 1 payment record should exist for orderId
            assertThat(paymentRepository.findByOrderId(orderId)).isPresent();
        });
    }

    @Test
    @DisplayName("orders.cancelled: Should refund authorized payment and emit PaymentRefunded outbox event")
    void handleOrderCancelled_shouldRefundPayment() throws Exception {
        UUID orderId = UUID.randomUUID();
        UUID customerId = UUID.randomUUID();
        UUID createEventId = UUID.randomUUID();

        // 1. Authorize payment first via orders.created
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
                        "customerId", customerId.toString(),
                        "totalAmount", "150.00",
                        "currency", "TRY"
                )
        );
        kafkaTemplate.send("orders.created", objectMapper.writeValueAsString(createEvent));

        await().atMost(10, TimeUnit.SECONDS).untilAsserted(() -> {
            assertThat(paymentRepository.findByOrderId(orderId)).isPresent();
        });

        Payment payment = paymentRepository.findByOrderId(orderId).orElseThrow();

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
                        "reason", "Inventory shortage compensation"
                )
        );
        kafkaTemplate.send("orders.cancelled", objectMapper.writeValueAsString(cancelEvent));

        // 3. Await refund and outbox event
        await().atMost(10, TimeUnit.SECONDS).untilAsserted(() -> {
            Payment updated = paymentRepository.findById(payment.getId()).orElseThrow();
            assertThat(updated.getStatus()).isEqualTo(PaymentStatus.REFUNDED);

            boolean outboxRefundExists = outboxEventRepository.findAll().stream()
                    .anyMatch(e -> "PaymentRefunded".equals(e.getType()) && payment.getId().toString().equals(e.getAggregateId()));
            assertThat(outboxRefundExists).isTrue();
        });
    }
}
