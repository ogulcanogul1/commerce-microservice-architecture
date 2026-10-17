package com.dgl.shipping.config;

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
    public NewTopic shipmentsCreatedTopic() {
        return TopicBuilder.name("shipments.created")
                .partitions(partitions)
                .replicas(replicationFactor)
                .build();
    }

    @Bean
    public NewTopic shipmentsCancelledTopic() {
        return TopicBuilder.name("shipments.cancelled")
                .partitions(partitions)
                .replicas(replicationFactor)
                .build();
    }

    @Bean
    public NewTopic shipmentsDeliveredTopic() {
        return TopicBuilder.name("shipments.delivered")
                .partitions(partitions)
                .replicas(replicationFactor)
                .build();
    }

    @Bean
    public NewTopic shipmentsCreatedDltTopic() {
        return TopicBuilder.name("shipments.created.DLT")
                .partitions(partitions)
                .replicas(replicationFactor)
                .build();
    }
}
