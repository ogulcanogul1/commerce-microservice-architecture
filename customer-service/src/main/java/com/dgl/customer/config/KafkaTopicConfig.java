package com.dgl.customer.config;

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
    public NewTopic customerCreatedTopic() {
        return TopicBuilder.name("customers.created")
                .partitions(partitions)
                .replicas(replicationFactor)
                .build();
    }

    @Bean
    public NewTopic customerUpdatedTopic() {
        return TopicBuilder.name("customers.updated")
                .partitions(partitions)
                .replicas(replicationFactor)
                .build();
    }
}
