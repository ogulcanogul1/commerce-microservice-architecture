package com.dgl.notification.cqrs.handler;

import com.dgl.notification.config.NotificationMetrics;
import com.dgl.notification.cqrs.command.MarkEventProcessedCommand;
import com.dgl.notification.cqrs.command.SendNotificationCommand;
import com.dgl.notification.cqrs.mapper.NotificationResponseMapper;
import com.dgl.notification.domain.Notification;
import com.dgl.notification.domain.NotificationChannel;
import com.dgl.notification.domain.NotificationStatus;
import com.dgl.notification.domain.ProcessedEvent;
import com.dgl.notification.dto.request.SendNotificationRequest;
import com.dgl.notification.dto.response.NotificationResponse;
import com.dgl.notification.repository.NotificationRepository;
import com.dgl.notification.repository.ProcessedEventRepository;
import com.dgl.notification.service.ChannelSender;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import java.time.Instant;
import java.util.List;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.*;

@ExtendWith(MockitoExtension.class)
class NotificationCommandHandlerTest {

    @Mock
    private NotificationRepository notificationRepository;

    @Mock
    private ProcessedEventRepository processedEventRepository;

    @Mock
    private ChannelSender emailSender;

    @Mock
    private ChannelSender smsSender;

    @Mock
    private NotificationMetrics notificationMetrics;

    private final NotificationResponseMapper responseMapper = new NotificationResponseMapper();

    private SendNotificationCommandHandler sendNotificationHandler;
    private MarkEventProcessedCommandHandler markEventProcessedHandler;

    @BeforeEach
    void setUp() {
        lenient().when(emailSender.getChannel()).thenReturn(NotificationChannel.EMAIL);
        lenient().when(smsSender.getChannel()).thenReturn(NotificationChannel.SMS);

        sendNotificationHandler = new SendNotificationCommandHandler(
                notificationRepository,
                responseMapper,
                List.of(emailSender, smsSender),
                notificationMetrics
        );

        markEventProcessedHandler = new MarkEventProcessedCommandHandler(processedEventRepository);
    }

    @Test
    @DisplayName("SendNotification: Success saves SENT notification")
    void sendNotification_success_shouldSaveSent() {
        UUID eventId = UUID.randomUUID();
        UUID customerId = UUID.randomUUID();
        SendNotificationRequest request = new SendNotificationRequest(
                customerId,
                NotificationChannel.EMAIL,
                "user@example.com",
                "Order Created",
                "Your order has been placed.",
                eventId
        );

        when(notificationRepository.save(any(Notification.class))).thenAnswer(invocation -> {
            Notification n = invocation.getArgument(0);
            n.setId(UUID.randomUUID());
            n.setCreatedAt(Instant.now());
            return n;
        });

        NotificationResponse response = sendNotificationHandler.handle(new SendNotificationCommand(request));

        assertThat(response).isNotNull();
        assertThat(response.status()).isEqualTo(NotificationStatus.SENT);
        assertThat(response.recipient()).isEqualTo("user@example.com");

        verify(emailSender).send("user@example.com", "Order Created", "Your order has been placed.");
        verify(notificationRepository).save(any(Notification.class));
    }

    @Test
    @DisplayName("SendNotification: Sender throws exception saves FAILED notification")
    void sendNotification_failure_shouldSaveFailed() {
        UUID eventId = UUID.randomUUID();
        SendNotificationRequest request = new SendNotificationRequest(
                null,
                NotificationChannel.SMS,
                "+905550000000",
                "SMS Alert",
                "Your payment failed",
                eventId
        );

        doThrow(new RuntimeException("SMS gateway down"))
                .when(smsSender).send(anyString(), anyString(), anyString());

        when(notificationRepository.save(any(Notification.class))).thenAnswer(invocation -> {
            Notification n = invocation.getArgument(0);
            n.setId(UUID.randomUUID());
            n.setCreatedAt(Instant.now());
            return n;
        });

        NotificationResponse response = sendNotificationHandler.handle(new SendNotificationCommand(request));

        assertThat(response.status()).isEqualTo(NotificationStatus.FAILED);
        assertThat(response.errorMessage()).isEqualTo("SMS gateway down");
    }

    @Test
    @DisplayName("SendNotification: Unconfigured sender throws IllegalArgumentException")
    void sendNotification_unconfiguredChannel_shouldThrow() {
        SendNotificationRequest request = new SendNotificationRequest(
                null,
                NotificationChannel.PUSH,
                "token",
                "Sub",
                "Body",
                UUID.randomUUID()
        );

        assertThatThrownBy(() -> sendNotificationHandler.handle(new SendNotificationCommand(request)))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessageContaining("No sender configured for channel: PUSH");
    }

    @Test
    @DisplayName("MarkEventProcessed: Saves ProcessedEvent to repository")
    void markEventProcessed_shouldSave() {
        UUID eventId = UUID.randomUUID();
        String group = "notification-group";

        markEventProcessedHandler.handle(new MarkEventProcessedCommand(group, eventId, "OrderConfirmed"));

        ArgumentCaptor<ProcessedEvent> captor = ArgumentCaptor.forClass(ProcessedEvent.class);
        verify(processedEventRepository).save(captor.capture());

        ProcessedEvent saved = captor.getValue();
        assertThat(saved.getId().getConsumerGroup()).isEqualTo(group);
        assertThat(saved.getId().getEventId()).isEqualTo(eventId);
        assertThat(saved.getEventType()).isEqualTo("OrderConfirmed");
    }
}
