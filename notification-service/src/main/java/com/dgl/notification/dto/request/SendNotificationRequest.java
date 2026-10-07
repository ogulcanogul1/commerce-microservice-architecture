package com.dgl.notification.dto.request;

import com.dgl.notification.domain.NotificationChannel;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

import java.util.UUID;

public record SendNotificationRequest(
    UUID customerId,

    @NotNull(message = "Channel is required")
    NotificationChannel channel,

    @NotBlank(message = "Recipient is required")
    String recipient,

    String subject,

    @NotBlank(message = "Content is required")
    String content,

    @NotNull(message = "Event ID is required")
    UUID eventId
) {}
