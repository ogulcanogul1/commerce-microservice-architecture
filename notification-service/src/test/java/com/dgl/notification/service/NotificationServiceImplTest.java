package com.dgl.notification.service;

import com.dgl.notification.cqrs.CommandBus;
import com.dgl.notification.cqrs.QueryBus;
import com.dgl.notification.cqrs.command.MarkEventProcessedCommand;
import com.dgl.notification.cqrs.command.SendNotificationCommand;
import com.dgl.notification.cqrs.query.GetNotificationByIdQuery;
import com.dgl.notification.cqrs.query.GetNotificationsByCustomerQuery;
import com.dgl.notification.cqrs.query.IsEventProcessedQuery;
import com.dgl.notification.domain.NotificationChannel;
import com.dgl.notification.dto.request.SendNotificationRequest;
import com.dgl.notification.dto.response.NotificationResponse;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import java.util.List;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.*;

@ExtendWith(MockitoExtension.class)
class NotificationServiceImplTest {

    @Mock
    private CommandBus commandBus;

    @Mock
    private QueryBus queryBus;

    @InjectMocks
    private NotificationServiceImpl notificationService;

    @Test
    @DisplayName("sendNotification: Should delegate to command bus")
    void sendNotification_shouldDelegate() {
        SendNotificationRequest request = new SendNotificationRequest(UUID.randomUUID(), NotificationChannel.EMAIL, "a@b.com", "Sub", "Body", UUID.randomUUID());
        NotificationResponse mockResponse = mock(NotificationResponse.class);
        when(commandBus.execute(any(SendNotificationCommand.class))).thenReturn(mockResponse);

        NotificationResponse actual = notificationService.sendNotification(request);

        assertThat(actual).isSameAs(mockResponse);
        verify(commandBus).execute(new SendNotificationCommand(request));
    }

    @Test
    @DisplayName("getNotificationById: Should delegate to query bus")
    void getNotificationById_shouldDelegate() {
        UUID id = UUID.randomUUID();
        NotificationResponse mockResponse = mock(NotificationResponse.class);
        when(queryBus.execute(any(GetNotificationByIdQuery.class))).thenReturn(mockResponse);

        NotificationResponse actual = notificationService.getNotificationById(id);

        assertThat(actual).isSameAs(mockResponse);
        verify(queryBus).execute(new GetNotificationByIdQuery(id));
    }

    @Test
    @DisplayName("getNotificationsByCustomer: Should delegate to query bus")
    void getNotificationsByCustomer_shouldDelegate() {
        UUID customerId = UUID.randomUUID();
        List<NotificationResponse> mockList = List.of();
        when(queryBus.execute(any(GetNotificationsByCustomerQuery.class))).thenReturn(mockList);

        List<NotificationResponse> actual = notificationService.getNotificationsByCustomer(customerId);

        assertThat(actual).isSameAs(mockList);
        verify(queryBus).execute(new GetNotificationsByCustomerQuery(customerId));
    }

    @Test
    @DisplayName("isEventProcessed: Should delegate to query bus")
    void isEventProcessed_shouldDelegate() {
        UUID eventId = UUID.randomUUID();
        when(queryBus.execute(any(IsEventProcessedQuery.class))).thenReturn(true);

        boolean actual = notificationService.isEventProcessed("group", eventId);

        assertThat(actual).isTrue();
        verify(queryBus).execute(new IsEventProcessedQuery("group", eventId));
    }

    @Test
    @DisplayName("markEventProcessed: Should delegate to command bus")
    void markEventProcessed_shouldDelegate() {
        UUID eventId = UUID.randomUUID();

        notificationService.markEventProcessed("group", eventId, "EventType");

        verify(commandBus).execute(new MarkEventProcessedCommand("group", eventId, "EventType"));
    }
}
