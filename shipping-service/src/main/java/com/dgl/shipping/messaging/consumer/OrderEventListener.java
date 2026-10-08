package com.dgl.shipping.messaging.consumer;

import com.dgl.shipping.domain.Carrier;
import com.dgl.shipping.domain.ProcessedEvent;
import com.dgl.shipping.domain.ProcessedEventId;
import com.dgl.shipping.domain.ShipmentStatus;
import com.dgl.shipping.dto.request.CreateShipmentRequest;
import com.dgl.shipping.dto.response.ShipmentResponse;
import com.dgl.shipping.exception.ShipmentNotFoundException;
import com.dgl.shipping.repository.ProcessedEventRepository;
import com.dgl.shipping.service.ShippingService;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;

import java.time.Instant;
import java.util.UUID;

@Slf4j
@Component
@RequiredArgsConstructor
public class OrderEventListener {

    private static final String CONSUMER_GROUP = "shipping-service-group";

    private final ShippingService shippingService;
    private final ProcessedEventRepository processedEventRepository;
    private final ObjectMapper objectMapper;

    @KafkaListener(topics = "orders.confirmed", groupId = CONSUMER_GROUP)
    @Transactional
    public void handleOrderConfirmed(String message) {
        try {
            JsonNode root = objectMapper.readTree(message);
            UUID eventId = UUID.fromString(root.path("eventId").asText());
            String eventType = root.path("eventType").asText();

            ProcessedEventId processedId = ProcessedEventId.builder()
                    .consumerGroup(CONSUMER_GROUP)
                    .eventId(eventId)
                    .build();

            if (processedEventRepository.existsById(processedId)) {
                log.info("Duplicate order confirmed event ignored for eventId: {}", eventId);
                return;
            }

            JsonNode payload = root.path("payload");
            UUID orderId = UUID.fromString(payload.path("orderId").asText());
            UUID customerId = payload.hasNonNull("customerId")
                    ? UUID.fromString(payload.path("customerId").asText())
                    : UUID.randomUUID();

            String deliveryAddress = payload.hasNonNull("shippingAddress")
                    ? payload.path("shippingAddress").asText()
                    : "Standard Customer Delivery Address";

            String recipientName = "Customer " + customerId.toString().substring(0, 8).toUpperCase();

            CreateShipmentRequest request = new CreateShipmentRequest(
                    orderId,
                    Carrier.YURTICI,
                    recipientName,
                    deliveryAddress
            );

            shippingService.createShipment(request);
            log.info("Shipment initiated for confirmed orderId: {}", orderId);

            processedEventRepository.save(ProcessedEvent.builder()
                    .id(processedId)
                    .eventType(eventType)
                    .processedAt(Instant.now())
                    .build());

        } catch (Exception ex) {
            log.error("Failed to process order confirmed event in shipping-service: {}", message, ex);
            throw new RuntimeException("Error processing OrderConfirmed event in shipping-service", ex);
        }
    }

    @KafkaListener(topics = "orders.cancelled", groupId = CONSUMER_GROUP)
    @Transactional
    public void handleOrderCancelled(String message) {
        try {
            JsonNode root = objectMapper.readTree(message);
            UUID eventId = UUID.fromString(root.path("eventId").asText());
            String eventType = root.path("eventType").asText();

            ProcessedEventId processedId = ProcessedEventId.builder()
                    .consumerGroup(CONSUMER_GROUP)
                    .eventId(eventId)
                    .build();

            if (processedEventRepository.existsById(processedId)) {
                log.info("Duplicate order cancelled event ignored for eventId: {}", eventId);
                return;
            }

            JsonNode payload = root.path("payload");
            UUID orderId = UUID.fromString(payload.path("orderId").asText());

            try {
                ShipmentResponse shipment = shippingService.getShipmentByOrderId(orderId);
                if (shipment.status() != ShipmentStatus.DELIVERED && shipment.status() != ShipmentStatus.CANCELLED) {
                    shippingService.cancelShipment(shipment.id(), "Order cancelled compensation");
                    log.info("Shipment cancelled for cancelled orderId: {}", orderId);
                }
            } catch (ShipmentNotFoundException ex) {
                log.debug("No active shipment found to cancel for orderId: {}", orderId);
            }

            processedEventRepository.save(ProcessedEvent.builder()
                    .id(processedId)
                    .eventType(eventType)
                    .processedAt(Instant.now())
                    .build());

        } catch (Exception ex) {
            log.error("Failed to process order cancelled event in shipping-service: {}", message, ex);
            throw new RuntimeException("Error processing OrderCancelled event in shipping-service", ex);
        }
    }
}
