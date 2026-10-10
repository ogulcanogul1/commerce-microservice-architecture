package com.dgl.shipping.cqrs.handler;

import com.dgl.shipping.cqrs.CommandHandler;
import com.dgl.shipping.cqrs.command.CancelShipmentCommand;
import com.dgl.shipping.cqrs.mapper.ShipmentResponseMapper;
import com.dgl.shipping.domain.Shipment;
import com.dgl.shipping.domain.ShipmentEvent;
import com.dgl.shipping.domain.ShipmentStatus;
import com.dgl.shipping.dto.response.ShipmentResponse;
import com.dgl.shipping.exception.InvalidShippingStateException;
import com.dgl.shipping.exception.ShipmentNotFoundException;
import com.dgl.shipping.messaging.event.ShipmentCancelledPayload;
import com.dgl.shipping.outbox.OutboxService;
import com.dgl.shipping.repository.ShipmentRepository;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;

import java.util.UUID;

@Component
@RequiredArgsConstructor
public class CancelShipmentCommandHandler implements CommandHandler<CancelShipmentCommand, ShipmentResponse> {

    private final ShipmentRepository shipmentRepository;
    private final OutboxService outboxService;
    private final ShipmentResponseMapper responseMapper;

    @Override
    @Transactional
    public ShipmentResponse handle(CancelShipmentCommand command) {
        UUID id = command.id();
        String reason = command.reason();

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

        return responseMapper.toResponse(shipment);
    }
}
