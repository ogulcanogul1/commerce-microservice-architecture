package com.dgl.shipping.cqrs.handler;

import com.dgl.shipping.cqrs.CommandHandler;
import com.dgl.shipping.cqrs.command.UpdateShipmentStatusCommand;
import com.dgl.shipping.cqrs.mapper.ShipmentResponseMapper;
import com.dgl.shipping.domain.Shipment;
import com.dgl.shipping.domain.ShipmentEvent;
import com.dgl.shipping.domain.ShipmentStatus;
import com.dgl.shipping.dto.request.UpdateShipmentStatusRequest;
import com.dgl.shipping.dto.response.ShipmentResponse;
import com.dgl.shipping.exception.InvalidShippingStateException;
import com.dgl.shipping.exception.ShipmentNotFoundException;
import com.dgl.shipping.messaging.event.ShipmentDeliveredPayload;
import com.dgl.shipping.outbox.OutboxService;
import com.dgl.shipping.repository.ShipmentRepository;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;

import java.time.Instant;
import java.util.UUID;

@Component
@RequiredArgsConstructor
public class UpdateShipmentStatusCommandHandler implements CommandHandler<UpdateShipmentStatusCommand, ShipmentResponse> {

    private final ShipmentRepository shipmentRepository;
    private final OutboxService outboxService;
    private final ShipmentResponseMapper responseMapper;

    @Override
    @Transactional
    public ShipmentResponse handle(UpdateShipmentStatusCommand command) {
        UUID id = command.id();
        UpdateShipmentStatusRequest request = command.request();

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

        return responseMapper.toResponse(shipment);
    }
}
