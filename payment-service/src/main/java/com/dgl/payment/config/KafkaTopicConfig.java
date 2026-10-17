package com.dgl.payment.config;

import org.apache.kafka.clients.admin.NewTopic;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.config.TopicBuilder;

@Configuration
public class KafkaTopicConfig {

    @Value("${kafka.topic.partitions:3}")
    private int partitions;

    @Value("${kafka.topic.replication-factor:1}")
    private short replicationFactor;

    @Bean
    public NewTopic paymentsAuthorizedTopic() {
        return TopicBuilder.name("payments.authorized")
                .partitions(partitions)
                .replicas(replicationFactor)
                .build();
    }

    @Bean
    public NewTopic paymentsCapturedTopic() {
        return TopicBuilder.name("payments.captured")
                .partitions(partitions)
                .replicas(replicationFactor)
                .build();
    }

    @Bean
    public NewTopic paymentsFailedTopic() {
        return TopicBuilder.name("payments.failed")
                .partitions(partitions)
                .replicas(replicationFactor)
                .build();
    }

    @Bean
    public NewTopic paymentsRefundedTopic() {
        return TopicBuilder.name("payments.refunded")
                .partitions(partitions)
                .replicas(replicationFactor)
                .build();
    }

    @Bean
    public NewTopic paymentsAuthorizedDltTopic() {
        return TopicBuilder.name("payments.authorized.DLT")
                .partitions(partitions)
                .replicas(replicationFactor)
                .build();
    }
}
