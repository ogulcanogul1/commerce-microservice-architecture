package com.dgl.order.outbox;

import com.dgl.order.messaging.event.EventEnvelope;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import io.micrometer.tracing.Tracer;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

import java.util.UUID;

@Slf4j
@Service
@RequiredArgsConstructor
public class OutboxServiceImpl implements OutboxService {

    private final OutboxEventRepository outboxEventRepository;
    private final ObjectMapper objectMapper;

    @Autowired(required = false)
    private Tracer tracer;

    @Override
    @Transactional(propagation = Propagation.MANDATORY)
    public <T> void recordEvent(String aggregateType, String aggregateId, String eventType, UUID correlationId, UUID causationId, T payload) {
        String traceparent = extractCurrentTraceparent();

        EventEnvelope<T> envelope = EventEnvelope.of(
                eventType,
                aggregateId,
                aggregateType,
                correlationId,
                causationId,
                traceparent,
                payload
        );

        try {
            String jsonPayload = objectMapper.writeValueAsString(envelope);
            String destination = resolveTopic(eventType);

            OutboxEvent outboxEvent = OutboxEvent.builder()
                    .aggregateType(aggregateType)
                    .aggregateId(aggregateId)
                    .type(eventType)
                    .destination(destination)
                    .payload(jsonPayload)
                    .status(OutboxStatus.PENDING)
                    .build();

            outboxEventRepository.save(outboxEvent);
            log.debug("Recorded order outbox event: {} to destination: {} for aggregate: {} [traceparent: {}]",
                    eventType, destination, aggregateId, traceparent);
        } catch (JsonProcessingException e) {
            log.error("Failed to serialize order outbox event payload for eventType: {}", eventType, e);
            throw new IllegalStateException("Failed to serialize outbox event payload", e);
        }
    }

    private String resolveTopic(String eventType) {
        return switch (eventType) {
            case "OrderCreated" -> "orders.created";
            case "OrderConfirmed" -> "orders.confirmed";
            case "OrderCancelled" -> "orders.cancelled";
            default -> "orders.events";
        };
    }

    private String extractCurrentTraceparent() {
        if (tracer != null && tracer.currentSpan() != null) {
            var context = tracer.currentSpan().context();
            return "00-" + context.traceId() + "-" + context.spanId() + "-01";
        }
        return null;
    }
}
