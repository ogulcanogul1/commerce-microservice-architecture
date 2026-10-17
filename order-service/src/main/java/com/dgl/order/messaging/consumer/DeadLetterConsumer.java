package com.dgl.order.messaging.consumer;

import com.dgl.order.domain.DeadLetterMessage;
import com.dgl.order.domain.DeadLetterStatus;
import com.dgl.order.repository.DeadLetterMessageRepository;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.apache.kafka.common.header.Header;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

import java.nio.charset.StandardCharsets;

@Component
@RequiredArgsConstructor
@Slf4j
public class DeadLetterConsumer {

    private final DeadLetterMessageRepository deadLetterMessageRepository;

    @KafkaListener(
            topics = {
                    "orders.created.DLT",
                    "inventory.reserved.DLT",
                    "payments.authorized.DLT",
                    "shipments.created.DLT"
            },
            groupId = "order-service-dlt-group",
            containerFactory = "kafkaListenerContainerFactory"
    )
    public void handleDeadLetterMessage(ConsumerRecord<String, String> record) {
        log.error("Received message in Dead Letter Topic: topic={}, key={}", record.topic(), record.key());

        String originalTopic = extractHeader(record, "kafka_dlt-original-topic");
        if (originalTopic == null || originalTopic.isBlank()) {
            originalTopic = record.topic().endsWith(".DLT")
                    ? record.topic().substring(0, record.topic().length() - 4)
                    : record.topic();
        }

        String exceptionMsg = extractHeader(record, "kafka_dlt-exception-message");

        DeadLetterMessage dltMessage = DeadLetterMessage.builder()
                .originalTopic(originalTopic)
                .originalKey(record.key())
                .payload(record.value())
                .exceptionMessage(exceptionMsg)
                .status(DeadLetterStatus.PENDING)
                .build();

        DeadLetterMessage saved = deadLetterMessageRepository.save(dltMessage);
        log.info("Persisted Dead Letter message: id={}, originalTopic={}, status={}",
                saved.getId(), originalTopic, saved.getStatus());
    }

    private String extractHeader(ConsumerRecord<String, String> record, String headerName) {
        Header header = record.headers().lastHeader(headerName);
        if (header != null && header.value() != null) {
            return new String(header.value(), StandardCharsets.UTF_8);
        }
        return null;
    }
}
