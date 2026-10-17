package com.dgl.product.config;

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
    public NewTopic productsCreatedTopic() {
        return TopicBuilder.name("products.created")
                .partitions(partitions)
                .replicas(replicationFactor)
                .build();
    }

    @Bean
    public NewTopic productsUpdatedTopic() {
        return TopicBuilder.name("products.updated")
                .partitions(partitions)
                .replicas(replicationFactor)
                .build();
    }

    @Bean
    public NewTopic productsDeletedTopic() {
        return TopicBuilder.name("products.deleted")
                .partitions(partitions)
                .replicas(replicationFactor)
                .build();
    }
}
