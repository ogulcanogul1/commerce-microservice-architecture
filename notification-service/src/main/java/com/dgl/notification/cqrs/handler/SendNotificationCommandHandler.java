package com.dgl.notification.cqrs.handler;

import com.dgl.notification.config.NotificationMetrics;
import com.dgl.notification.cqrs.CommandHandler;
import com.dgl.notification.cqrs.command.SendNotificationCommand;
import com.dgl.notification.cqrs.mapper.NotificationResponseMapper;
import com.dgl.notification.domain.Notification;
import com.dgl.notification.domain.NotificationChannel;
import com.dgl.notification.domain.NotificationStatus;
import com.dgl.notification.dto.request.SendNotificationRequest;
import com.dgl.notification.dto.response.NotificationResponse;
import com.dgl.notification.repository.NotificationRepository;
import com.dgl.notification.service.ChannelSender;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;

import java.time.Instant;
import java.util.List;
import java.util.Map;
import java.util.function.Function;
import java.util.stream.Collectors;

@Slf4j
@Component
public class SendNotificationCommandHandler implements CommandHandler<SendNotificationCommand, NotificationResponse> {

    private final NotificationRepository notificationRepository;
    private final NotificationResponseMapper responseMapper;
    private final Map<NotificationChannel, ChannelSender> senders;
    private final NotificationMetrics notificationMetrics;

    public SendNotificationCommandHandler(
            NotificationRepository notificationRepository,
            NotificationResponseMapper responseMapper,
            List<ChannelSender> channelSenders,
            @Autowired(required = false) NotificationMetrics notificationMetrics) {
        this.notificationRepository = notificationRepository;
        this.responseMapper = responseMapper;
        this.senders = channelSenders.stream()
                .collect(Collectors.toMap(ChannelSender::getChannel, Function.identity()));
        this.notificationMetrics = notificationMetrics;
    }

    @Override
    @Transactional
    public NotificationResponse handle(SendNotificationCommand command) {
        SendNotificationRequest request = command.request();
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
        return responseMapper.toResponse(saved);
    }
}
