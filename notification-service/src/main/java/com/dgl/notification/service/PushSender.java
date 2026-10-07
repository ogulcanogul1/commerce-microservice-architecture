package com.dgl.notification.service;

import com.dgl.notification.domain.NotificationChannel;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Component;

@Slf4j
@Component
public class PushSender implements ChannelSender {

    @Override
    public NotificationChannel getChannel() {
        return NotificationChannel.PUSH;
    }

    @Override
    public void send(String recipient, String subject, String content) {
        log.info("[SIMULATED PUSH] Sending Push notification to user '{}' -> {} : {}", recipient, subject, content);
    }
}
