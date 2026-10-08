package com.dgl.inventory.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.config.ConcurrentKafkaListenerContainerFactory;
import org.springframework.kafka.core.ConsumerFactory;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.listener.DeadLetterPublishingRecoverer;
import org.springframework.kafka.listener.DefaultErrorHandler;
import org.springframework.util.backoff.FixedBackOff;

@Configuration
public class KafkaConsumerConfig {

    @Bean
    public ConcurrentKafkaListenerContainerFactory<String, String> kafkaListenerContainerFactory(
            ConsumerFactory<String, String> consumerFactory,
            KafkaTemplate<String, String> kafkaTemplate) {

        ConcurrentKafkaListenerContainerFactory<String, String> factory =
                new ConcurrentKafkaListenerContainerFactory<>();
        factory.setConsumerFactory(consumerFactory);
        factory.getContainerProperties().setObservationEnabled(true);
        kafkaTemplate.setObservationEnabled(true);

        factory.setRecordInterceptor(new org.springframework.kafka.listener.RecordInterceptor<>() {
            @Override
            public org.apache.kafka.clients.consumer.ConsumerRecord<String, String> intercept(
                    org.apache.kafka.clients.consumer.ConsumerRecord<String, String> record,
                    org.apache.kafka.clients.consumer.Consumer<String, String> consumer) {
                org.apache.kafka.common.header.Header header = record.headers().lastHeader("X-Correlation-Id");
                if (header != null && header.value() != null) {
                    org.slf4j.MDC.put("correlationId", new String(header.value(), java.nio.charset.StandardCharsets.UTF_8));
                }
                return record;
            }

            @Override
            public void afterRecord(
                    org.apache.kafka.clients.consumer.ConsumerRecord<String, String> record,
                    org.apache.kafka.clients.consumer.Consumer<String, String> consumer) {
                org.slf4j.MDC.remove("correlationId");
            }
        });

        DeadLetterPublishingRecoverer recoverer = new DeadLetterPublishingRecoverer(kafkaTemplate);
        DefaultErrorHandler errorHandler = new DefaultErrorHandler(recoverer, new FixedBackOff(1000L, 3L));
        errorHandler.addNotRetryableExceptions(
                com.dgl.inventory.exception.BusinessRuleException.class,
                com.fasterxml.jackson.core.JsonProcessingException.class,
                IllegalArgumentException.class
        );
        factory.setCommonErrorHandler(errorHandler);

        return factory;
    }
}
