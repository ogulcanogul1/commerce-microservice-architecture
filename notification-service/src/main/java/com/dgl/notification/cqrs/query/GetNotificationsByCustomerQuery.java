package com.dgl.notification.cqrs.query;

import com.dgl.notification.cqrs.Query;
import com.dgl.notification.dto.response.NotificationResponse;

import java.util.List;
import java.util.UUID;

public record GetNotificationsByCustomerQuery(UUID customerId) implements Query<List<NotificationResponse>> {
}
