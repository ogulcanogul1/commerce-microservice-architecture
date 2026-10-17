package com.dgl.order.domain;

import jakarta.persistence.*;
import lombok.*;
import org.hibernate.annotations.CreationTimestamp;

import java.time.Instant;
import java.util.UUID;

@Entity
@Table(name = "dead_letter_messages", indexes = {
        @Index(name = "idx_dead_letter_status", columnList = "status"),
        @Index(name = "idx_dead_letter_original_topic", columnList = "original_topic"),
        @Index(name = "idx_dead_letter_created_at", columnList = "created_at")
})
@Getter
@Setter
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class DeadLetterMessage {

    @Id
    @GeneratedValue(strategy = GenerationType.UUID)
    private UUID id;

    @Column(name = "original_topic", nullable = false, length = 150)
    private String originalTopic;

    @Column(name = "original_key", length = 255)
    private String originalKey;

    @Column(nullable = false, columnDefinition = "TEXT")
    private String payload;

    @Column(name = "exception_message", columnDefinition = "TEXT")
    private String exceptionMessage;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 30)
    @Builder.Default
    private DeadLetterStatus status = DeadLetterStatus.PENDING;

    @CreationTimestamp
    @Column(name = "created_at", nullable = false, updatable = false)
    private Instant createdAt;

    @Column(name = "replayed_at")
    private Instant replayedAt;
}
