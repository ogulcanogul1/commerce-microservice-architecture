package com.dgl.order.config;

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
    public NewTopic ordersCreatedTopic() {
        return TopicBuilder.name("orders.created")
                .partitions(partitions)
                .replicas(replicationFactor)
                .build();
    }

    @Bean
    public NewTopic ordersConfirmedTopic() {
        return TopicBuilder.name("orders.confirmed")
                .partitions(partitions)
                .replicas(replicationFactor)
                .build();
    }

    @Bean
    public NewTopic ordersCancelledTopic() {
        return TopicBuilder.name("orders.cancelled")
                .partitions(partitions)
                .replicas(replicationFactor)
                .build();
    }

    @Bean
    public NewTopic ordersCreatedDltTopic() {
        return TopicBuilder.name("orders.created.DLT")
                .partitions(partitions)
                .replicas(replicationFactor)
                .build();
    }
}
