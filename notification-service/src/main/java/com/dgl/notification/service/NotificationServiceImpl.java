package com.dgl.notification.service;

import com.dgl.notification.cqrs.CommandBus;
import com.dgl.notification.cqrs.QueryBus;
import com.dgl.notification.cqrs.command.MarkEventProcessedCommand;
import com.dgl.notification.cqrs.command.SendNotificationCommand;
import com.dgl.notification.cqrs.query.GetNotificationByIdQuery;
import com.dgl.notification.cqrs.query.GetNotificationsByCustomerQuery;
import com.dgl.notification.cqrs.query.IsEventProcessedQuery;
import com.dgl.notification.dto.request.SendNotificationRequest;
import com.dgl.notification.dto.response.NotificationResponse;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;

import java.util.List;
import java.util.UUID;

@Service
@RequiredArgsConstructor
public class NotificationServiceImpl implements NotificationService {

    private final CommandBus commandBus;
    private final QueryBus queryBus;

    @Override
    public NotificationResponse sendNotification(SendNotificationRequest request) {
        return commandBus.execute(new SendNotificationCommand(request));
    }

    @Override
    public NotificationResponse getNotificationById(UUID id) {
        return queryBus.execute(new GetNotificationByIdQuery(id));
    }

    @Override
    public List<NotificationResponse> getNotificationsByCustomer(UUID customerId) {
        return queryBus.execute(new GetNotificationsByCustomerQuery(customerId));
    }

    @Override
    public boolean isEventProcessed(String consumerGroup, UUID eventId) {
        return Boolean.TRUE.equals(queryBus.execute(new IsEventProcessedQuery(consumerGroup, eventId)));
    }

    @Override
    public void markEventProcessed(String consumerGroup, UUID eventId, String eventType) {
        commandBus.execute(new MarkEventProcessedCommand(consumerGroup, eventId, eventType));
    }
}
