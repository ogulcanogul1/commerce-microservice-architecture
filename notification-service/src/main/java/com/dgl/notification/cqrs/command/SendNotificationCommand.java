package com.dgl.notification.cqrs.command;

import com.dgl.notification.cqrs.Command;
import com.dgl.notification.dto.request.SendNotificationRequest;
import com.dgl.notification.dto.response.NotificationResponse;

public record SendNotificationCommand(SendNotificationRequest request) implements Command<NotificationResponse> {
}
