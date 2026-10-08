package com.dgl.notification.service;

import com.dgl.notification.domain.*;
import com.dgl.notification.dto.request.SendNotificationRequest;
import com.dgl.notification.dto.response.NotificationResponse;
import com.dgl.notification.exception.NotificationNotFoundException;
import com.dgl.notification.repository.NotificationRepository;
import com.dgl.notification.repository.ProcessedEventRepository;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.Instant;
import java.util.*;
import java.util.function.Function;
import java.util.stream.Collectors;

@Slf4j
@Service
@Transactional(readOnly = true)
public class NotificationServiceImpl implements NotificationService {

    private final NotificationRepository notificationRepository;
    private final ProcessedEventRepository processedEventRepository;
    private final Map<NotificationChannel, ChannelSender> senders;

    @org.springframework.beans.factory.annotation.Autowired(required = false)
    private com.dgl.notification.config.NotificationMetrics notificationMetrics;

    public NotificationServiceImpl(
            NotificationRepository notificationRepository,
            ProcessedEventRepository processedEventRepository,
            List<ChannelSender> channelSenders) {
        this.notificationRepository = notificationRepository;
        this.processedEventRepository = processedEventRepository;
        this.senders = channelSenders.stream()
                .collect(Collectors.toMap(ChannelSender::getChannel, Function.identity()));
    }

    @Override
    @Transactional
    public NotificationResponse sendNotification(SendNotificationRequest request) {
        ChannelSender sender = senders.get(request.channel());
        if (sender == null) {
            throw new IllegalArgumentException("No sender configured for channel: " + request.channel());
        }

        NotificationStatus status = NotificationStatus.SENT;
        String errorMessage = null;
        Instant sentAt = Instant.now();

        try {
            sender.send(request.recipient(), request.subject(), request.content());
            if (notificationMetrics != null) {
                notificationMetrics.incrementSent(request.channel());
            }
        } catch (Exception ex) {
            log.error("Failed to send notification via {}: {}", request.channel(), ex.getMessage(), ex);
            status = NotificationStatus.FAILED;
            errorMessage = ex.getMessage();
            if (notificationMetrics != null) {
                notificationMetrics.incrementFailed(request.channel());
            }
        }

        Notification notification = Notification.builder()
                .customerId(request.customerId())
                .channel(request.channel())
                .recipient(request.recipient())
                .subject(request.subject())
                .content(request.content())
                .status(status)
                .eventId(request.eventId())
                .errorMessage(errorMessage)
                .sentAt(sentAt)
                .build();

        Notification saved = notificationRepository.save(notification);
        return mapToResponse(saved);
    }

    @Override
    public NotificationResponse getNotificationById(UUID id) {
        Notification notification = notificationRepository.findById(id)
                .orElseThrow(() -> new NotificationNotFoundException(id));
        return mapToResponse(notification);
    }

    @Override
    public List<NotificationResponse> getNotificationsByCustomer(UUID customerId) {
        return notificationRepository.findByCustomerIdOrderByCreatedAtDesc(customerId).stream()
                .map(this::mapToResponse)
                .toList();
    }

    @Override
    public boolean isEventProcessed(String consumerGroup, UUID eventId) {
        ProcessedEventId id = ProcessedEventId.builder()
                .consumerGroup(consumerGroup)
                .eventId(eventId)
                .build();
        return processedEventRepository.existsById(id);
    }

    @Override
    @Transactional
    public void markEventProcessed(String consumerGroup, UUID eventId, String eventType) {
        ProcessedEventId id = ProcessedEventId.builder()
                .consumerGroup(consumerGroup)
                .eventId(eventId)
                .build();

        ProcessedEvent event = ProcessedEvent.builder()
                .id(id)
                .eventType(eventType)
                .build();

        processedEventRepository.save(event);
    }

    private NotificationResponse mapToResponse(Notification notification) {
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
