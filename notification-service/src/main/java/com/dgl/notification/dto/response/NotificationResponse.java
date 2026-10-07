package com.dgl.notification.dto.response;

import com.dgl.notification.domain.NotificationChannel;
import com.dgl.notification.domain.NotificationStatus;

import java.time.Instant;
import java.util.UUID;

public record NotificationResponse(
    UUID id,
    UUID customerId,
    NotificationChannel channel,
    String recipient,
    String subject,
    String content,
    NotificationStatus status,
    UUID eventId,
    String errorMessage,
    Instant sentAt,
    Instant createdAt
) {}
