package com.dgl.payment.outbox;

import com.dgl.payment.messaging.event.EventEnvelope;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
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

    @Override
    @Transactional(propagation = Propagation.MANDATORY)
    public <T> void recordEvent(String aggregateType, String aggregateId, String eventType, UUID correlationId, UUID causationId, T payload) {
        EventEnvelope<T> envelope = EventEnvelope.of(
                eventType,
                aggregateId,
                aggregateType,
                correlationId,
                causationId,
                payload
        );

        try {
            String jsonPayload = objectMapper.writeValueAsString(envelope);

            OutboxEvent outboxEvent = OutboxEvent.builder()
                    .aggregateType(aggregateType)
                    .aggregateId(aggregateId)
                    .type(eventType)
                    .payload(jsonPayload)
                    .status(OutboxStatus.PENDING)
                    .build();

            outboxEventRepository.save(outboxEvent);
            log.debug("Recorded payment outbox event: {} for aggregate: {}", eventType, aggregateId);
        } catch (JsonProcessingException e) {
            log.error("Failed to serialize payment outbox event payload for eventType: {}", eventType, e);
            throw new IllegalStateException("Failed to serialize outbox event payload", e);
        }
    }
}
