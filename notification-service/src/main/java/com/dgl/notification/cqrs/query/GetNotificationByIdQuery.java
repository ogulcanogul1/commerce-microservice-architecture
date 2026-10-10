package com.dgl.notification.cqrs.query;

import com.dgl.notification.cqrs.Query;
import com.dgl.notification.dto.response.NotificationResponse;

import java.util.UUID;

public record GetNotificationByIdQuery(UUID id) implements Query<NotificationResponse> {
}
