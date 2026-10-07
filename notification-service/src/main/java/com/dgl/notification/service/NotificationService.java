package com.dgl.notification.service;

import com.dgl.notification.dto.request.SendNotificationRequest;
import com.dgl.notification.dto.response.NotificationResponse;

import java.util.List;
import java.util.UUID;

public interface NotificationService {

    NotificationResponse sendNotification(SendNotificationRequest request);

    NotificationResponse getNotificationById(UUID id);

    List<NotificationResponse> getNotificationsByCustomer(UUID customerId);

    boolean isEventProcessed(String consumerGroup, UUID eventId);

    void markEventProcessed(String consumerGroup, UUID eventId, String eventType);
}
