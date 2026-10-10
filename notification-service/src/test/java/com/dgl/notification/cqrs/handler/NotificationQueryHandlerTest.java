package com.dgl.notification.cqrs.handler;

import com.dgl.notification.cqrs.mapper.NotificationResponseMapper;
import com.dgl.notification.cqrs.query.GetNotificationByIdQuery;
import com.dgl.notification.cqrs.query.GetNotificationsByCustomerQuery;
import com.dgl.notification.cqrs.query.IsEventProcessedQuery;
import com.dgl.notification.domain.Notification;
import com.dgl.notification.domain.NotificationChannel;
import com.dgl.notification.domain.NotificationStatus;
import com.dgl.notification.domain.ProcessedEventId;
import com.dgl.notification.dto.response.NotificationResponse;
import com.dgl.notification.exception.NotificationNotFoundException;
import com.dgl.notification.repository.NotificationRepository;
import com.dgl.notification.repository.ProcessedEventRepository;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import java.time.Instant;
import java.util.List;
import java.util.Optional;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class NotificationQueryHandlerTest {

    @Mock
    private NotificationRepository notificationRepository;

    @Mock
    private ProcessedEventRepository processedEventRepository;

    private final NotificationResponseMapper responseMapper = new NotificationResponseMapper();

    private GetNotificationByIdQueryHandler getByIdHandler;
    private GetNotificationsByCustomerQueryHandler getByCustomerHandler;
    private IsEventProcessedQueryHandler isProcessedHandler;

    private UUID notificationId;
    private UUID customerId;
    private Notification sampleNotification;

    @BeforeEach
    void setUp() {
        getByIdHandler = new GetNotificationByIdQueryHandler(notificationRepository, responseMapper);
        getByCustomerHandler = new GetNotificationsByCustomerQueryHandler(notificationRepository, responseMapper);
        isProcessedHandler = new IsEventProcessedQueryHandler(processedEventRepository);

        notificationId = UUID.randomUUID();
        customerId = UUID.randomUUID();

        sampleNotification = Notification.builder()
                .id(notificationId)
                .customerId(customerId)
                .channel(NotificationChannel.EMAIL)
                .recipient("test@example.com")
                .subject("Test Subject")
                .content("Test Content")
                .status(NotificationStatus.SENT)
                .eventId(UUID.randomUUID())
                .createdAt(Instant.now())
                .build();
    }

    @Test
    @DisplayName("getNotificationById: Found returns NotificationResponse")
    void getNotificationById_found_shouldReturn() {
        when(notificationRepository.findById(notificationId)).thenReturn(Optional.of(sampleNotification));

        NotificationResponse response = getByIdHandler.handle(new GetNotificationByIdQuery(notificationId));

        assertThat(response).isNotNull();
        assertThat(response.id()).isEqualTo(notificationId);
        assertThat(response.recipient()).isEqualTo("test@example.com");
    }

    @Test
    @DisplayName("getNotificationById: Not found throws NotificationNotFoundException")
    void getNotificationById_notFound_shouldThrow() {
        when(notificationRepository.findById(notificationId)).thenReturn(Optional.empty());

        assertThatThrownBy(() -> getByIdHandler.handle(new GetNotificationByIdQuery(notificationId)))
                .isInstanceOf(NotificationNotFoundException.class);
    }

    @Test
    @DisplayName("getNotificationsByCustomer: Returns list of notifications")
    void getNotificationsByCustomer_shouldReturnList() {
        when(notificationRepository.findByCustomerIdOrderByCreatedAtDesc(customerId)).thenReturn(List.of(sampleNotification));

        List<NotificationResponse> list = getByCustomerHandler.handle(new GetNotificationsByCustomerQuery(customerId));

        assertThat(list).hasSize(1);
        assertThat(list.getFirst().customerId()).isEqualTo(customerId);
    }

    @Test
    @DisplayName("isEventProcessed: Returns existsById result")
    void isEventProcessed_shouldReturnBoolean() {
        UUID eventId = UUID.randomUUID();
        String group = "notification-group";
        ProcessedEventId id = ProcessedEventId.builder().consumerGroup(group).eventId(eventId).build();

        when(processedEventRepository.existsById(id)).thenReturn(true);

        Boolean result = isProcessedHandler.handle(new IsEventProcessedQuery(group, eventId));

        assertThat(result).isTrue();
    }
}
