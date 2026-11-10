package com.dgl.shipping.cqrs.handler;

import com.dgl.shipping.cqrs.CommandHandler;
import com.dgl.shipping.cqrs.command.CreateShipmentCommand;
import com.dgl.shipping.cqrs.mapper.ShipmentResponseMapper;
import com.dgl.shipping.domain.Shipment;
import com.dgl.shipping.domain.ShipmentEvent;
import com.dgl.shipping.domain.ShipmentStatus;
import com.dgl.shipping.dto.request.CreateShipmentRequest;
import com.dgl.shipping.dto.response.ShipmentResponse;
import com.dgl.shipping.messaging.event.ShipmentCreatedPayload;
import com.dgl.shipping.outbox.OutboxService;
import com.dgl.shipping.repository.ShipmentRepository;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;

import java.time.Duration;
import java.time.Instant;
import java.util.ArrayList;
import java.util.UUID;

@Component
@RequiredArgsConstructor
public class CreateShipmentCommandHandler implements CommandHandler<CreateShipmentCommand, ShipmentResponse> {

    private final ShipmentRepository shipmentRepository;
    private final OutboxService outboxService;
    private final ShipmentResponseMapper responseMapper;

    @Override
    @Transactional
    public ShipmentResponse handle(CreateShipmentCommand command) {
        CreateShipmentRequest request = command.request();
        String trackingNumber = "TRK-" + UUID.randomUUID().toString().substring(0, 10).toUpperCase();

        Shipment shipment = Shipment.builder()
                .orderId(request.orderId())
                .customerId(request.customerId())
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

        return responseMapper.toResponse(saved);
    }
}
