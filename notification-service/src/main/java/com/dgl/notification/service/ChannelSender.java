package com.dgl.notification.service;

import com.dgl.notification.domain.NotificationChannel;

public interface ChannelSender {

    NotificationChannel getChannel();

    void send(String recipient, String subject, String content);
}
