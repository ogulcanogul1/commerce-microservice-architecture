package com.dgl.notification.service;

import com.dgl.notification.domain.NotificationChannel;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Component;

@Slf4j
@Component
public class EmailSender implements ChannelSender {

    @Override
    public NotificationChannel getChannel() {
        return NotificationChannel.EMAIL;
    }

    @Override
    public void send(String recipient, String subject, String content) {
        log.info("[SIMULATED EMAIL] Sending email to '{}' with subject '{}' -> {}", recipient, subject, content);
    }
}
