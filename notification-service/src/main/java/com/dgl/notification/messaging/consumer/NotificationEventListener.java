package com.dgl.notification.messaging.consumer;

import com.dgl.notification.domain.NotificationChannel;
import com.dgl.notification.dto.request.SendNotificationRequest;
import com.dgl.notification.service.NotificationService;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;

import java.util.UUID;

@Slf4j
@Component
@RequiredArgsConstructor
public class NotificationEventListener {

    private static final String CONSUMER_GROUP = "notification-service-group";

    private final NotificationService notificationService;
    private final ObjectMapper objectMapper;

    @KafkaListener(topics = "orders.confirmed", groupId = CONSUMER_GROUP)
    @Transactional
    public void handleOrderConfirmed(String message) {
        try {
            JsonNode root = objectMapper.readTree(message);
            UUID eventId = UUID.fromString(root.path("eventId").asText());
            String eventType = root.path("eventType").asText();

            if (notificationService.isEventProcessed(CONSUMER_GROUP, eventId)) {
                log.info("Duplicate order confirmed notification event ignored for eventId: {}", eventId);
                return;
            }

            JsonNode payload = root.path("payload");
            UUID orderId = UUID.fromString(payload.path("orderId").asText());
            String orderNumber = payload.hasNonNull("orderNumber") ? payload.path("orderNumber").asText() : orderId.toString();
            UUID customerId = payload.hasNonNull("customerId")
                    ? UUID.fromString(payload.path("customerId").asText())
                    : null;
            String totalAmount = payload.hasNonNull("totalAmount") ? payload.path("totalAmount").asText() : "";

            String recipient = customerId != null ? "customer-" + customerId + "@example.com" : "customer@example.com";
            String subject = "Order Confirmed - " + orderNumber;
            String content = "Your order " + orderNumber + " with total amount " + totalAmount
                    + " has been confirmed and is being prepared for shipment.";

            SendNotificationRequest request = new SendNotificationRequest(
                    customerId,
                    NotificationChannel.EMAIL,
                    recipient,
                    subject,
                    content,
                    eventId
            );

            notificationService.sendNotification(request);
            notificationService.markEventProcessed(CONSUMER_GROUP, eventId, eventType);
            log.info("Order confirmation notification sent for order: {}", orderNumber);

        } catch (Exception ex) {
            log.error("Failed to process OrderConfirmed event in notification-service: {}", message, ex);
            throw new RuntimeException("Error processing OrderConfirmed event in notification-service", ex);
        }
    }

    @KafkaListener(topics = "orders.cancelled", groupId = CONSUMER_GROUP)
    @Transactional
    public void handleOrderCancelled(String message) {
        try {
            JsonNode root = objectMapper.readTree(message);
            UUID eventId = UUID.fromString(root.path("eventId").asText());
            String eventType = root.path("eventType").asText();

            if (notificationService.isEventProcessed(CONSUMER_GROUP, eventId)) {
                log.info("Duplicate order cancelled notification event ignored for eventId: {}", eventId);
                return;
            }

            JsonNode payload = root.path("payload");
            UUID orderId = UUID.fromString(payload.path("orderId").asText());
            String orderNumber = payload.hasNonNull("orderNumber") ? payload.path("orderNumber").asText() : orderId.toString();
            String reason = payload.hasNonNull("reason") ? payload.path("reason").asText() : "Order cancellation";

            String recipient = "order-" + orderId + "@example.com";
            String subject = "Order Cancelled - " + orderNumber;
            String content = "Your order " + orderNumber + " has been cancelled. Reason: " + reason;

            SendNotificationRequest request = new SendNotificationRequest(
                    null,
                    NotificationChannel.EMAIL,
                    recipient,
                    subject,
                    content,
                    eventId
            );

            notificationService.sendNotification(request);
            notificationService.markEventProcessed(CONSUMER_GROUP, eventId, eventType);
            log.info("Order cancellation notification sent for order: {}", orderNumber);

        } catch (Exception ex) {
            log.error("Failed to process OrderCancelled event in notification-service: {}", message, ex);
            throw new RuntimeException("Error processing OrderCancelled event in notification-service", ex);
        }
    }

    @KafkaListener(topics = "payments.failed", groupId = CONSUMER_GROUP)
    @Transactional
    public void handlePaymentFailed(String message) {
        try {
            JsonNode root = objectMapper.readTree(message);
            UUID eventId = UUID.fromString(root.path("eventId").asText());
            String eventType = root.path("eventType").asText();

            if (notificationService.isEventProcessed(CONSUMER_GROUP, eventId)) {
                log.info("Duplicate payment failed notification event ignored for eventId: {}", eventId);
                return;
            }

            JsonNode payload = root.path("payload");
            UUID orderId = UUID.fromString(payload.path("orderId").asText());
            String reason = payload.hasNonNull("reason") ? payload.path("reason").asText() : "Payment rejected";

            SendNotificationRequest request = new SendNotificationRequest(
                    null,
                    NotificationChannel.SMS,
                    "+905550000000",
                    "Payment Issue",
                    "Payment failed for order " + orderId + ". Reason: " + reason,
                    eventId
            );

            notificationService.sendNotification(request);
            notificationService.markEventProcessed(CONSUMER_GROUP, eventId, eventType);
            log.info("Payment failure notification sent for orderId: {}", orderId);

        } catch (Exception ex) {
            log.error("Failed to process PaymentFailed event in notification-service: {}", message, ex);
            throw new RuntimeException("Error processing PaymentFailed event in notification-service", ex);
        }
    }

    @KafkaListener(topics = "shipments.created", groupId = CONSUMER_GROUP)
    @Transactional
    public void handleShipmentCreated(String message) {
        try {
            JsonNode root = objectMapper.readTree(message);
            UUID eventId = UUID.fromString(root.path("eventId").asText());
            String eventType = root.path("eventType").asText();

            if (notificationService.isEventProcessed(CONSUMER_GROUP, eventId)) {
                log.info("Duplicate shipment created notification event ignored for eventId: {}", eventId);
                return;
            }

            JsonNode payload = root.path("payload");
            UUID orderId = UUID.fromString(payload.path("orderId").asText());
            String trackingNumber = payload.hasNonNull("trackingNumber") ? payload.path("trackingNumber").asText() : "N/A";
            String carrier = payload.hasNonNull("carrier") ? payload.path("carrier").asText() : "Courier";

            SendNotificationRequest request = new SendNotificationRequest(
                    null,
                    NotificationChannel.SMS,
                    "+905550000000",
                    "Shipment Update",
                    "Your order " + orderId + " has been shipped via " + carrier + ". Tracking number: " + trackingNumber,
                    eventId
            );

            notificationService.sendNotification(request);
            notificationService.markEventProcessed(CONSUMER_GROUP, eventId, eventType);
            log.info("Shipment created notification sent for tracking number: {}", trackingNumber);

        } catch (Exception ex) {
            log.error("Failed to process ShipmentCreated event in notification-service: {}", message, ex);
            throw new RuntimeException("Error processing ShipmentCreated event in notification-service", ex);
        }
    }

    @KafkaListener(topics = "shipments.delivered", groupId = CONSUMER_GROUP)
    @Transactional
    public void handleShipmentDelivered(String message) {
        try {
            JsonNode root = objectMapper.readTree(message);
            UUID eventId = UUID.fromString(root.path("eventId").asText());
            String eventType = root.path("eventType").asText();

            if (notificationService.isEventProcessed(CONSUMER_GROUP, eventId)) {
                log.info("Duplicate shipment delivered notification event ignored for eventId: {}", eventId);
                return;
            }

            JsonNode payload = root.path("payload");
            String trackingNumber = payload.hasNonNull("trackingNumber") ? payload.path("trackingNumber").asText() : "N/A";

            SendNotificationRequest request = new SendNotificationRequest(
                    null,
                    NotificationChannel.PUSH,
                    "customer-device-token",
                    "Delivery Completed",
                    "Your shipment with tracking number " + trackingNumber + " has been delivered!",
                    eventId
            );

            notificationService.sendNotification(request);
            notificationService.markEventProcessed(CONSUMER_GROUP, eventId, eventType);
            log.info("Shipment delivered notification sent for tracking number: {}", trackingNumber);

        } catch (Exception ex) {
            log.error("Failed to process ShipmentDelivered event in notification-service: {}", message, ex);
            throw new RuntimeException("Error processing ShipmentDelivered event in notification-service", ex);
        }
    }
}
