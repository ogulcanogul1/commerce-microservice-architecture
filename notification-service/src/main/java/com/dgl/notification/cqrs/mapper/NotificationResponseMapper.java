package com.dgl.notification.cqrs.mapper;

import com.dgl.notification.domain.Notification;
import com.dgl.notification.dto.response.NotificationResponse;
import org.springframework.stereotype.Component;

@Component
public class NotificationResponseMapper {

    public NotificationResponse toResponse(Notification notification) {
        if (notification == null) {
            return null;
        }

        return new NotificationResponse(
                notification.getId(),
                notification.getCustomerId(),
                notification.getChannel(),
                notification.getRecipient(),
                notification.getSubject(),
                notification.getContent(),
                notification.getStatus(),
                notification.getEventId(),
                notification.getErrorMessage(),
                notification.getSentAt(),
                notification.getCreatedAt()
        );
    }
}
