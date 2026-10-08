package com.dgl.notification.messaging;

import com.dgl.notification.domain.Notification;
import com.dgl.notification.domain.NotificationChannel;
import com.dgl.notification.domain.NotificationStatus;
import com.dgl.notification.repository.NotificationRepository;
import com.dgl.notification.repository.ProcessedEventRepository;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.test.context.EmbeddedKafka;
import org.springframework.test.annotation.DirtiesContext;

import java.time.Instant;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.TimeUnit;

import static org.assertj.core.api.Assertions.assertThat;
import static org.awaitility.Awaitility.await;

@SpringBootTest
@DirtiesContext
@EmbeddedKafka(
        partitions = 1,
        topics = {
                "orders.confirmed",
                "orders.cancelled",
                "payments.failed",
                "shipments.created",
                "shipments.delivered"
        }
)
class NotificationEventListenerIntegrationTest {

    @Autowired
    private KafkaTemplate<String, String> kafkaTemplate;

    @Autowired
    private NotificationRepository notificationRepository;

    @Autowired
    private ProcessedEventRepository processedEventRepository;

    @Autowired
    private ObjectMapper objectMapper;

    @BeforeEach
    void cleanUp() {
        notificationRepository.deleteAll();
        processedEventRepository.deleteAll();
    }

    @Test
    @DisplayName("orders.confirmed event should trigger email notification and mark event as processed")
    void handleOrderConfirmed_ShouldSendEmailNotificationAndMarkProcessed() throws Exception {
        UUID eventId = UUID.randomUUID();
        UUID orderId = UUID.randomUUID();
        UUID customerId = UUID.randomUUID();

        Map<String, Object> payload = Map.of(
                "orderId", orderId.toString(),
                "orderNumber", "ORD-1001",
                "customerId", customerId.toString(),
                "totalAmount", "450.00"
        );

        String message = createEventEnvelope(eventId, "OrderConfirmed", orderId.toString(), "Order", payload);

        kafkaTemplate.send("orders.confirmed", orderId.toString(), message).get();

        await().atMost(10, TimeUnit.SECONDS).untilAsserted(() -> {
            List<Notification> notifications = notificationRepository.findAll();
            assertThat(notifications).hasSize(1);

            Notification notification = notifications.getFirst();
            assertThat(notification.getChannel()).isEqualTo(NotificationChannel.EMAIL);
            assertThat(notification.getRecipient()).isEqualTo("customer-" + customerId + "@example.com");
            assertThat(notification.getSubject()).contains("ORD-1001");
            assertThat(notification.getStatus()).isEqualTo(NotificationStatus.SENT);
            assertThat(notification.getEventId()).isEqualTo(eventId);

            assertThat(processedEventRepository.count()).isEqualTo(1);
        });
    }

    @Test
    @DisplayName("Duplicate orders.confirmed event should be ignored idempotently without duplicating notifications")
    void handleOrderConfirmed_WhenDuplicateEvent_ShouldBeIdempotent() throws Exception {
        UUID eventId = UUID.randomUUID();
        UUID orderId = UUID.randomUUID();
        UUID customerId = UUID.randomUUID();

        Map<String, Object> payload = Map.of(
                "orderId", orderId.toString(),
                "orderNumber", "ORD-1002",
                "customerId", customerId.toString(),
                "totalAmount", "120.00"
        );

        String message = createEventEnvelope(eventId, "OrderConfirmed", orderId.toString(), "Order", payload);

        // Send first event
        kafkaTemplate.send("orders.confirmed", orderId.toString(), message).get();

        await().atMost(10, TimeUnit.SECONDS).untilAsserted(() ->
                assertThat(notificationRepository.findAll()).hasSize(1)
        );

        // Send duplicate event with identical eventId
        kafkaTemplate.send("orders.confirmed", orderId.toString(), message).get();

        // Ensure count remains 1 after a short delay
        TimeUnit.SECONDS.sleep(2);
        assertThat(notificationRepository.findAll()).hasSize(1);
    }

    @Test
    @DisplayName("orders.cancelled event should trigger cancellation email notification")
    void handleOrderCancelled_ShouldSendEmailNotification() throws Exception {
        UUID eventId = UUID.randomUUID();
        UUID orderId = UUID.randomUUID();

        Map<String, Object> payload = Map.of(
                "orderId", orderId.toString(),
                "orderNumber", "ORD-9999",
                "reason", "Insufficient inventory stock"
        );

        String message = createEventEnvelope(eventId, "OrderCancelled", orderId.toString(), "Order", payload);

        kafkaTemplate.send("orders.cancelled", orderId.toString(), message).get();

        await().atMost(10, TimeUnit.SECONDS).untilAsserted(() -> {
            List<Notification> notifications = notificationRepository.findAll();
            assertThat(notifications).hasSize(1);

            Notification notification = notifications.getFirst();
            assertThat(notification.getChannel()).isEqualTo(NotificationChannel.EMAIL);
            assertThat(notification.getRecipient()).isEqualTo("order-" + orderId + "@example.com");
            assertThat(notification.getSubject()).contains("Order Cancelled - ORD-9999");
            assertThat(notification.getContent()).contains("Insufficient inventory stock");
            assertThat(notification.getStatus()).isEqualTo(NotificationStatus.SENT);
        });
    }

    @Test
    @DisplayName("payments.failed event should trigger SMS alert notification")
    void handlePaymentFailed_ShouldSendSmsNotification() throws Exception {
        UUID eventId = UUID.randomUUID();
        UUID orderId = UUID.randomUUID();

        Map<String, Object> payload = Map.of(
                "orderId", orderId.toString(),
                "reason", "Insufficient funds"
        );

        String message = createEventEnvelope(eventId, "PaymentFailed", orderId.toString(), "Payment", payload);

        kafkaTemplate.send("payments.failed", orderId.toString(), message).get();

        await().atMost(10, TimeUnit.SECONDS).untilAsserted(() -> {
            List<Notification> notifications = notificationRepository.findAll();
            assertThat(notifications).hasSize(1);

            Notification notification = notifications.getFirst();
            assertThat(notification.getChannel()).isEqualTo(NotificationChannel.SMS);
            assertThat(notification.getRecipient()).isEqualTo("+905550000000");
            assertThat(notification.getSubject()).isEqualTo("Payment Issue");
            assertThat(notification.getContent()).contains("Insufficient funds");
        });
    }

    @Test
    @DisplayName("shipments.created event should trigger SMS notification with tracking number")
    void handleShipmentCreated_ShouldSendSmsNotification() throws Exception {
        UUID eventId = UUID.randomUUID();
        UUID orderId = UUID.randomUUID();

        Map<String, Object> payload = Map.of(
                "orderId", orderId.toString(),
                "trackingNumber", "TRK-777888",
                "carrier", "Yurtici Kargo"
        );

        String message = createEventEnvelope(eventId, "ShipmentCreated", orderId.toString(), "Shipment", payload);

        kafkaTemplate.send("shipments.created", orderId.toString(), message).get();

        await().atMost(10, TimeUnit.SECONDS).untilAsserted(() -> {
            List<Notification> notifications = notificationRepository.findAll();
            assertThat(notifications).hasSize(1);

            Notification notification = notifications.getFirst();
            assertThat(notification.getChannel()).isEqualTo(NotificationChannel.SMS);
            assertThat(notification.getContent()).contains("TRK-777888");
            assertThat(notification.getContent()).contains("Yurtici Kargo");
        });
    }

    @Test
    @DisplayName("shipments.delivered event should trigger push notification")
    void handleShipmentDelivered_ShouldSendPushNotification() throws Exception {
        UUID eventId = UUID.randomUUID();
        UUID orderId = UUID.randomUUID();

        Map<String, Object> payload = Map.of(
                "orderId", orderId.toString(),
                "trackingNumber", "TRK-777888"
        );

        String message = createEventEnvelope(eventId, "ShipmentDelivered", orderId.toString(), "Shipment", payload);

        kafkaTemplate.send("shipments.delivered", orderId.toString(), message).get();

        await().atMost(10, TimeUnit.SECONDS).untilAsserted(() -> {
            List<Notification> notifications = notificationRepository.findAll();
            assertThat(notifications).hasSize(1);

            Notification notification = notifications.getFirst();
            assertThat(notification.getChannel()).isEqualTo(NotificationChannel.PUSH);
            assertThat(notification.getRecipient()).isEqualTo("customer-device-token");
            assertThat(notification.getContent()).contains("delivered");
        });
    }

    private String createEventEnvelope(UUID eventId, String eventType, String aggregateId,
                                       String aggregateType, Map<String, Object> payload) throws Exception {
        Map<String, Object> envelope = new HashMap<>();
        envelope.put("eventId", eventId.toString());
        envelope.put("eventType", eventType);
        envelope.put("aggregateId", aggregateId);
        envelope.put("aggregateType", aggregateType);
        envelope.put("timestamp", Instant.now().toString());
        envelope.put("version", 1);
        envelope.put("correlationId", UUID.randomUUID().toString());
        envelope.put("causationId", UUID.randomUUID().toString());
        envelope.put("payload", payload);

        return objectMapper.writeValueAsString(envelope);
    }
}
