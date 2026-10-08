package com.dgl.payment.messaging.consumer;

import com.dgl.payment.domain.PaymentStatus;
import com.dgl.payment.domain.ProcessedEvent;
import com.dgl.payment.domain.ProcessedEventId;
import com.dgl.payment.dto.request.ProcessPaymentRequest;
import com.dgl.payment.dto.request.RefundPaymentRequest;
import com.dgl.payment.dto.response.PaymentResponse;
import com.dgl.payment.exception.PaymentNotFoundException;
import com.dgl.payment.messaging.event.PaymentFailedPayload;
import com.dgl.payment.outbox.OutboxService;
import com.dgl.payment.repository.ProcessedEventRepository;
import com.dgl.payment.service.PaymentService;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.UUID;

@Slf4j
@Component
@RequiredArgsConstructor
public class OrderEventListener {

    private static final String CONSUMER_GROUP = "payment-service-group";

    private final PaymentService paymentService;
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
            UUID customerId = UUID.fromString(payload.path("customerId").asText());
            BigDecimal totalAmount = new BigDecimal(payload.path("totalAmount").asText());
            String currency = payload.hasNonNull("currency") ? payload.path("currency").asText() : "TRY";

            try {
                ProcessPaymentRequest paymentRequest = new ProcessPaymentRequest(
                        orderId,
                        customerId,
                        totalAmount,
                        currency,
                        "CREDIT_CARD"
                );
                paymentService.processPayment(paymentRequest, "ORDER-" + orderId);
                log.info("Payment authorized successfully for orderId: {}", orderId);
            } catch (Exception ex) {
                log.error("Payment authorization failed for orderId: {}. Reason: {}", orderId, ex.getMessage());
                outboxService.recordEvent(
                        "Payment",
                        orderId.toString(),
                        "PaymentFailed",
                        correlationId,
                        eventId,
                        new PaymentFailedPayload(null, orderId, totalAmount, ex.getMessage())
                );
            }

            processedEventRepository.save(ProcessedEvent.builder()
                    .id(processedId)
                    .eventType(eventType)
                    .processedAt(Instant.now())
                    .build());

        } catch (Exception ex) {
            log.error("Failed to process order created event in payment-service: {}", message, ex);
            throw new RuntimeException("Error processing OrderCreated event in payment-service", ex);
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

            try {
                PaymentResponse payment = paymentService.getPaymentByOrderId(orderId);
                if (payment.status() == PaymentStatus.AUTHORIZED || payment.status() == PaymentStatus.CAPTURED) {
                    paymentService.refundPayment(payment.id(), new RefundPaymentRequest(payment.amount(), "Order cancelled compensation"));
                    log.info("Payment refunded successfully for cancelled orderId: {}", orderId);
                }
            } catch (PaymentNotFoundException ex) {
                log.debug("No active payment found to refund for cancelled orderId: {}", orderId);
            }

            processedEventRepository.save(ProcessedEvent.builder()
                    .id(processedId)
                    .eventType(eventType)
                    .processedAt(Instant.now())
                    .build());

        } catch (Exception ex) {
            log.error("Failed to process order cancelled event in payment-service: {}", message, ex);
            throw new RuntimeException("Error processing OrderCancelled event in payment-service", ex);
        }
    }
}
