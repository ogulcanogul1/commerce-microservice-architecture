package com.dgl.order.dto.response;

import com.dgl.order.domain.DeadLetterStatus;

import java.time.Instant;
import java.util.UUID;

public record DeadLetterMessageResponse(
        UUID id,
        String originalTopic,
        String originalKey,
        String payload,
        String exceptionMessage,
        DeadLetterStatus status,
        Instant createdAt,
        Instant replayedAt
) {
}
