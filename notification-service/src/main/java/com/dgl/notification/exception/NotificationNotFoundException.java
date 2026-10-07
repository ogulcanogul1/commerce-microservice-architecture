package com.dgl.notification.exception;

import java.util.UUID;

public class NotificationNotFoundException extends RuntimeException {

    public NotificationNotFoundException(UUID id) {
        super("Notification not found with ID: " + id);
    }

    public NotificationNotFoundException(String message) {
        super(message);
    }
}
