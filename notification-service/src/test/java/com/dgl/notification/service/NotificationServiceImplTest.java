package com.dgl.notification.service;

import com.dgl.notification.domain.*;
import com.dgl.notification.dto.request.SendNotificationRequest;
import com.dgl.notification.dto.response.NotificationResponse;
import com.dgl.notification.exception.NotificationNotFoundException;
import com.dgl.notification.repository.NotificationRepository;
import com.dgl.notification.repository.ProcessedEventRepository;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import java.time.Instant;
import java.util.List;
import java.util.Optional;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.*;

@ExtendWith(MockitoExtension.class)
class NotificationServiceImplTest {

    @Mock
    private NotificationRepository notificationRepository;

    @Mock
    private ProcessedEventRepository processedEventRepository;

    @Mock
    private ChannelSender emailSender;

    @Mock
    private ChannelSender smsSender;

    private NotificationServiceImpl notificationService;

    @BeforeEach
    void setUp() {
        lenient().when(emailSender.getChannel()).thenReturn(NotificationChannel.EMAIL);
        lenient().when(smsSender.getChannel()).thenReturn(NotificationChannel.SMS);

        notificationService = new NotificationServiceImpl(
                notificationRepository,
                processedEventRepository,
                List.of(emailSender, smsSender)
        );
    }

    @Test
    @DisplayName("sendNotification should succeed and persist SENT notification when channel sender succeeds")
    void sendNotification_WhenSenderSucceeds_ShouldSaveSentNotification() {
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

        NotificationResponse response = notificationService.sendNotification(request);

        assertThat(response).isNotNull();
        assertThat(response.status()).isEqualTo(NotificationStatus.SENT);
        assertThat(response.recipient()).isEqualTo("user@example.com");
        assertThat(response.subject()).isEqualTo("Order Created");
        assertThat(response.errorMessage()).isNull();

        verify(emailSender, times(1)).send("user@example.com", "Order Created", "Your order has been placed.");
        verify(notificationRepository, times(1)).save(any(Notification.class));
    }

    @Test
    @DisplayName("sendNotification should capture failure and persist FAILED notification when sender throws exception")
    void sendNotification_WhenSenderThrowsException_ShouldSaveFailedNotification() {
        UUID eventId = UUID.randomUUID();
        SendNotificationRequest request = new SendNotificationRequest(
                null,
                NotificationChannel.SMS,
                "+905550000000",
                "SMS Alert",
                "Your payment failed",
                eventId
        );

        doThrow(new RuntimeException("SMS gateway unreachable"))
                .when(smsSender).send(anyString(), anyString(), anyString());

        when(notificationRepository.save(any(Notification.class))).thenAnswer(invocation -> {
            Notification n = invocation.getArgument(0);
            n.setId(UUID.randomUUID());
            n.setCreatedAt(Instant.now());
            return n;
        });

        NotificationResponse response = notificationService.sendNotification(request);

        assertThat(response).isNotNull();
        assertThat(response.status()).isEqualTo(NotificationStatus.FAILED);
        assertThat(response.errorMessage()).isEqualTo("SMS gateway unreachable");

        verify(smsSender, times(1)).send("+905550000000", "SMS Alert", "Your payment failed");
        verify(notificationRepository, times(1)).save(any(Notification.class));
    }

    @Test
    @DisplayName("sendNotification should throw IllegalArgumentException when no sender is configured for channel")
    void sendNotification_WhenNoSenderConfigured_ShouldThrowException() {
        SendNotificationRequest request = new SendNotificationRequest(
                null,
                NotificationChannel.PUSH,
                "token123",
                "Push",
                "Hello",
                UUID.randomUUID()
        );

        assertThatThrownBy(() -> notificationService.sendNotification(request))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessageContaining("No sender configured for channel: PUSH");

        verifyNoInteractions(notificationRepository);
    }

    @Test
    @DisplayName("getNotificationById should return response when notification exists")
    void getNotificationById_WhenExists_ShouldReturnResponse() {
        UUID id = UUID.randomUUID();
        Notification notification = Notification.builder()
                .id(id)
                .channel(NotificationChannel.EMAIL)
                .recipient("test@example.com")
                .subject("Test Subject")
                .content("Test Content")
                .status(NotificationStatus.SENT)
                .eventId(UUID.randomUUID())
                .createdAt(Instant.now())
                .build();

        when(notificationRepository.findById(id)).thenReturn(Optional.of(notification));

        NotificationResponse response = notificationService.getNotificationById(id);

        assertThat(response).isNotNull();
        assertThat(response.id()).isEqualTo(id);
        assertThat(response.recipient()).isEqualTo("test@example.com");
    }

    @Test
    @DisplayName("getNotificationById should throw NotificationNotFoundException when notification does not exist")
    void getNotificationById_WhenNotFound_ShouldThrowException() {
        UUID id = UUID.randomUUID();
        when(notificationRepository.findById(id)).thenReturn(Optional.empty());

        assertThatThrownBy(() -> notificationService.getNotificationById(id))
                .isInstanceOf(NotificationNotFoundException.class);
    }

    @Test
    @DisplayName("getNotificationsByCustomer should return mapped list of notifications")
    void getNotificationsByCustomer_ShouldReturnList() {
        UUID customerId = UUID.randomUUID();
        Notification notification = Notification.builder()
                .id(UUID.randomUUID())
                .customerId(customerId)
                .channel(NotificationChannel.EMAIL)
                .recipient("customer@example.com")
                .subject("Welcome")
                .content("Welcome to our platform")
                .status(NotificationStatus.SENT)
                .eventId(UUID.randomUUID())
                .createdAt(Instant.now())
                .build();

        when(notificationRepository.findByCustomerIdOrderByCreatedAtDesc(customerId))
                .thenReturn(List.of(notification));

        List<NotificationResponse> result = notificationService.getNotificationsByCustomer(customerId);

        assertThat(result).hasSize(1);
        assertThat(result.getFirst().customerId()).isEqualTo(customerId);
    }

    @Test
    @DisplayName("isEventProcessed should return repository existsById result")
    void isEventProcessed_ShouldDelegateToRepository() {
        UUID eventId = UUID.randomUUID();
        String group = "notification-service-group";
        ProcessedEventId processedEventId = ProcessedEventId.builder()
                .consumerGroup(group)
                .eventId(eventId)
                .build();

        when(processedEventRepository.existsById(processedEventId)).thenReturn(true);

        boolean exists = notificationService.isEventProcessed(group, eventId);

        assertThat(exists).isTrue();
        verify(processedEventRepository, times(1)).existsById(processedEventId);
    }

    @Test
    @DisplayName("markEventProcessed should save ProcessedEvent with correct composite key")
    void markEventProcessed_ShouldSaveProcessedEvent() {
        UUID eventId = UUID.randomUUID();
        String group = "notification-service-group";

        notificationService.markEventProcessed(group, eventId, "OrderConfirmed");

        ArgumentCaptor<ProcessedEvent> captor = ArgumentCaptor.forClass(ProcessedEvent.class);
        verify(processedEventRepository, times(1)).save(captor.capture());

        ProcessedEvent saved = captor.getValue();
        assertThat(saved.getId().getConsumerGroup()).isEqualTo(group);
        assertThat(saved.getId().getEventId()).isEqualTo(eventId);
        assertThat(saved.getEventType()).isEqualTo("OrderConfirmed");
    }
}
