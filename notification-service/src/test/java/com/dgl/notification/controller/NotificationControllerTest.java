package com.dgl.notification.controller;

import com.dgl.notification.cqrs.CommandBus;
import com.dgl.notification.cqrs.QueryBus;
import com.dgl.notification.cqrs.command.SendNotificationCommand;
import com.dgl.notification.cqrs.query.GetNotificationByIdQuery;
import com.dgl.notification.cqrs.query.GetNotificationsByCustomerQuery;
import com.dgl.notification.domain.NotificationChannel;
import com.dgl.notification.domain.NotificationStatus;
import com.dgl.notification.dto.request.SendNotificationRequest;
import com.dgl.notification.dto.response.NotificationResponse;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;

import java.time.Instant;
import java.util.List;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.*;

@ExtendWith(MockitoExtension.class)
class NotificationControllerTest {

    @Mock
    private CommandBus commandBus;

    @Mock
    private QueryBus queryBus;

    @InjectMocks
    private NotificationController controller;

    private UUID notificationId;
    private NotificationResponse mockNotificationResponse;

    @BeforeEach
    void setUp() {
        notificationId = UUID.randomUUID();
        mockNotificationResponse = new NotificationResponse(
                notificationId,
                UUID.randomUUID(),
                NotificationChannel.EMAIL,
                "a@b.com",
                "Subject",
                "Content",
                NotificationStatus.SENT,
                UUID.randomUUID(),
                null,
                Instant.now(),
                Instant.now()
        );
    }

    @Test
    @DisplayName("sendNotification: Should dispatch command and return 201 Created")
    void sendNotification_shouldReturn201() {
        SendNotificationRequest request = new SendNotificationRequest(UUID.randomUUID(), NotificationChannel.EMAIL, "a@b.com", "Subject", "Content", UUID.randomUUID());
        when(commandBus.execute(any(SendNotificationCommand.class))).thenReturn(mockNotificationResponse);

        ResponseEntity<NotificationResponse> response = controller.sendNotification(request);

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.CREATED);
        assertThat(response.getBody()).isSameAs(mockNotificationResponse);
        verify(commandBus).execute(new SendNotificationCommand(request));
    }

    @Test
    @DisplayName("getNotificationById: Should dispatch query and return 200 OK")
    void getNotificationById_shouldReturn200() {
        when(queryBus.execute(any(GetNotificationByIdQuery.class))).thenReturn(mockNotificationResponse);

        ResponseEntity<NotificationResponse> response = controller.getNotificationById(notificationId);

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(response.getBody()).isSameAs(mockNotificationResponse);
        verify(queryBus).execute(new GetNotificationByIdQuery(notificationId));
    }

    @Test
    @DisplayName("getNotificationsByCustomer: Should dispatch query and return 200 OK")
    void getNotificationsByCustomer_shouldReturn200() {
        UUID customerId = UUID.randomUUID();
        when(queryBus.execute(any(GetNotificationsByCustomerQuery.class))).thenReturn(List.of(mockNotificationResponse));

        ResponseEntity<List<NotificationResponse>> response = controller.getNotificationsByCustomer(customerId);

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(response.getBody()).hasSize(1);
        verify(queryBus).execute(new GetNotificationsByCustomerQuery(customerId));
    }
}
