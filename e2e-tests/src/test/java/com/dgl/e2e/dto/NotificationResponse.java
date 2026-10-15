package com.dgl.e2e.dto;

import java.util.UUID;

public record NotificationResponse(
        UUID id,
        UUID customerId,
        String channel,
        String recipient,
        String subject,
        String message,
        String status
) {}
