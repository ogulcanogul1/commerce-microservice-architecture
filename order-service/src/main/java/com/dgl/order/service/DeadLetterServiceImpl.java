package com.dgl.order.service;

import com.dgl.order.domain.DeadLetterMessage;
import com.dgl.order.domain.DeadLetterStatus;
import com.dgl.order.dto.response.DeadLetterMessageResponse;
import com.dgl.order.repository.DeadLetterMessageRepository;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.Instant;
import java.util.UUID;

@Service
@RequiredArgsConstructor
@Slf4j
public class DeadLetterServiceImpl implements DeadLetterService {

    private final DeadLetterMessageRepository repository;
    private final KafkaTemplate<String, String> kafkaTemplate;

    @Override
    @Transactional(readOnly = true)
    public Page<DeadLetterMessageResponse> getDeadLetters(DeadLetterStatus status, Pageable pageable) {
        Page<DeadLetterMessage> page = (status != null)
                ? repository.findByStatus(status, pageable)
                : repository.findAll(pageable);
        return page.map(this::toResponse);
    }

    @Override
    @Transactional
    public DeadLetterMessageResponse replayDeadLetter(UUID id) {
        DeadLetterMessage message = repository.findById(id)
                .orElseThrow(() -> new IllegalArgumentException("Dead letter message not found: " + id));

        log.info("Replaying dead letter message id: {} back to topic: {}", id, message.getOriginalTopic());
        if (message.getOriginalKey() != null) {
            kafkaTemplate.send(message.getOriginalTopic(), message.getOriginalKey(), message.getPayload());
        } else {
            kafkaTemplate.send(message.getOriginalTopic(), message.getPayload());
        }

        message.setStatus(DeadLetterStatus.REPLAYED);
        message.setReplayedAt(Instant.now());
        DeadLetterMessage saved = repository.save(message);

        return toResponse(saved);
    }

    @Override
    @Transactional
    public DeadLetterMessageResponse discardDeadLetter(UUID id) {
        DeadLetterMessage message = repository.findById(id)
                .orElseThrow(() -> new IllegalArgumentException("Dead letter message not found: " + id));

        message.setStatus(DeadLetterStatus.DISCARDED);
        DeadLetterMessage saved = repository.save(message);
        log.info("Discarded dead letter message id: {}", id);

        return toResponse(saved);
    }

    private DeadLetterMessageResponse toResponse(DeadLetterMessage entity) {
        return new DeadLetterMessageResponse(
                entity.getId(),
                entity.getOriginalTopic(),
                entity.getOriginalKey(),
                entity.getPayload(),
                entity.getExceptionMessage(),
                entity.getStatus(),
                entity.getCreatedAt(),
                entity.getReplayedAt()
        );
    }
}
