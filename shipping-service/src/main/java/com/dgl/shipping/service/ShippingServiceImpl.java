package com.dgl.shipping.service;

import com.dgl.shipping.domain.Shipment;
import com.dgl.shipping.domain.ShipmentEvent;
import com.dgl.shipping.domain.ShipmentStatus;
import com.dgl.shipping.dto.request.CreateShipmentRequest;
import com.dgl.shipping.dto.request.UpdateShipmentStatusRequest;
import com.dgl.shipping.dto.response.ShipmentEventResponse;
import com.dgl.shipping.dto.response.ShipmentResponse;
import com.dgl.shipping.dto.response.TrackingResponse;
import com.dgl.shipping.exception.InvalidShippingStateException;
import com.dgl.shipping.exception.ShipmentNotFoundException;
import com.dgl.shipping.messaging.event.ShipmentCancelledPayload;
import com.dgl.shipping.messaging.event.ShipmentCreatedPayload;
import com.dgl.shipping.messaging.event.ShipmentDeliveredPayload;
import com.dgl.shipping.outbox.OutboxService;
import com.dgl.shipping.repository.ShipmentEventRepository;
import com.dgl.shipping.repository.ShipmentRepository;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.Duration;
import java.time.Instant;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.UUID;

@Service
@RequiredArgsConstructor
@Transactional(readOnly = true)
public class ShippingServiceImpl implements ShippingService {

    private final ShipmentRepository shipmentRepository;
    private final ShipmentEventRepository shipmentEventRepository;
    private final OutboxService outboxService;

    @Override
    @Transactional
    public ShipmentResponse createShipment(CreateShipmentRequest request) {
        String trackingNumber = "TRK-" + UUID.randomUUID().toString().substring(0, 10).toUpperCase();

        Shipment shipment = Shipment.builder()
                .orderId(request.orderId())
                .trackingNumber(trackingNumber)
                .carrier(request.carrier())
                .status(ShipmentStatus.CREATED)
                .recipientName(request.recipientName())
                .deliveryAddress(request.deliveryAddress())
                .estimatedDelivery(Instant.now().plus(Duration.ofDays(3)))
                .events(new ArrayList<>())
                .build();

        ShipmentEvent initialEvent = ShipmentEvent.builder()
                .shipment(shipment)
                .status(ShipmentStatus.CREATED.name())
                .description("Shipment created, waiting for pickup by " + request.carrier().name())
                .location("Transfer Center")
                .build();
        shipment.getEvents().add(initialEvent);

        Shipment saved = shipmentRepository.save(shipment);

        outboxService.recordEvent(
                "Shipment",
                saved.getId().toString(),
                "ShipmentCreated",
                null,
                null,
                new ShipmentCreatedPayload(
                        saved.getId(),
                        saved.getOrderId(),
                        saved.getTrackingNumber(),
                        saved.getCarrier().name(),
                        saved.getRecipientName(),
                        saved.getDeliveryAddress(),
                        saved.getEstimatedDelivery()
                )
        );

        return mapToResponse(saved);
    }

    @Override
    public ShipmentResponse getShipmentById(UUID id) {
        Shipment shipment = shipmentRepository.findById(id)
                .orElseThrow(() -> new ShipmentNotFoundException(id));
        return mapToResponse(shipment);
    }

    @Override
    public ShipmentResponse getShipmentByOrderId(UUID orderId) {
        Shipment shipment = shipmentRepository.findByOrderId(orderId)
                .orElseThrow(() -> new ShipmentNotFoundException("Shipment not found for order: " + orderId));
        return mapToResponse(shipment);
    }

    @Override
    public TrackingResponse trackShipment(String trackingNumber) {
        Shipment shipment = shipmentRepository.findByTrackingNumber(trackingNumber)
                .orElseThrow(() -> new ShipmentNotFoundException("Shipment not found with tracking number: " + trackingNumber));

        List<ShipmentEventResponse> eventResponses = shipment.getEvents() != null
                ? shipment.getEvents().stream().map(this::mapEventToResponse).toList()
                : Collections.emptyList();

        return new TrackingResponse(
                shipment.getTrackingNumber(),
                shipment.getCarrier(),
                shipment.getStatus(),
                shipment.getEstimatedDelivery(),
                shipment.getActualDelivery(),
                eventResponses
        );
    }

    @Override
    @Transactional
    public ShipmentResponse updateShipmentStatus(UUID id, UpdateShipmentStatusRequest request) {
        Shipment shipment = shipmentRepository.findById(id)
                .orElseThrow(() -> new ShipmentNotFoundException(id));

        if (shipment.getStatus() == ShipmentStatus.DELIVERED || shipment.getStatus() == ShipmentStatus.CANCELLED) {
            throw new InvalidShippingStateException("Cannot update status of a " + shipment.getStatus() + " shipment");
        }

        shipment.setStatus(request.status());
        if (request.status() == ShipmentStatus.DELIVERED) {
            shipment.setActualDelivery(Instant.now());
        }

        ShipmentEvent event = ShipmentEvent.builder()
                .shipment(shipment)
                .status(request.status().name())
                .description(request.description() != null ? request.description() : "Shipment status updated to " + request.status())
                .location(request.location() != null ? request.location() : "In Transit")
                .build();
        shipment.getEvents().add(event);

        if (request.status() == ShipmentStatus.DELIVERED) {
            outboxService.recordEvent(
                    "Shipment",
                    shipment.getId().toString(),
                    "ShipmentDelivered",
                    null,
                    null,
                    new ShipmentDeliveredPayload(
                            shipment.getId(),
                            shipment.getOrderId(),
                            shipment.getTrackingNumber(),
                            shipment.getActualDelivery()
                    )
            );
        }

        return mapToResponse(shipment);
    }

    @Override
    @Transactional
    public ShipmentResponse cancelShipment(UUID id, String reason) {
        Shipment shipment = shipmentRepository.findById(id)
                .orElseThrow(() -> new ShipmentNotFoundException(id));

        if (shipment.getStatus() == ShipmentStatus.DELIVERED) {
            throw new InvalidShippingStateException("Delivered shipment cannot be cancelled");
        }

        shipment.setStatus(ShipmentStatus.CANCELLED);
        shipment.setFailureReason(reason);

        ShipmentEvent event = ShipmentEvent.builder()
                .shipment(shipment)
                .status(ShipmentStatus.CANCELLED.name())
                .description("Shipment cancelled: " + reason)
                .location("Logistics Center")
                .build();
        shipment.getEvents().add(event);

        outboxService.recordEvent(
                "Shipment",
                shipment.getId().toString(),
                "ShipmentCancelled",
                null,
                null,
                new ShipmentCancelledPayload(
                        shipment.getId(),
                        shipment.getOrderId(),
                        shipment.getTrackingNumber(),
                        reason
                )
        );

        return mapToResponse(shipment);
    }

    private ShipmentResponse mapToResponse(Shipment shipment) {
        List<ShipmentEventResponse> eventResponses = shipment.getEvents() != null
                ? shipment.getEvents().stream().map(this::mapEventToResponse).toList()
                : Collections.emptyList();

        return new ShipmentResponse(
                shipment.getId(),
                shipment.getOrderId(),
                shipment.getTrackingNumber(),
                shipment.getCarrier(),
                shipment.getStatus(),
                shipment.getRecipientName(),
                shipment.getDeliveryAddress(),
                shipment.getEstimatedDelivery(),
                shipment.getActualDelivery(),
                shipment.getFailureReason(),
                eventResponses,
                shipment.getCreatedAt(),
                shipment.getUpdatedAt()
        );
    }

    private ShipmentEventResponse mapEventToResponse(ShipmentEvent event) {
        return new ShipmentEventResponse(
                event.getId(),
                event.getStatus(),
                event.getDescription(),
                event.getLocation(),
                event.getEventTime()
        );
    }
}
