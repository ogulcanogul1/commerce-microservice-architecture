package com.dgl.shipping.cqrs.mapper;

import com.dgl.shipping.domain.Shipment;
import com.dgl.shipping.domain.ShipmentEvent;
import com.dgl.shipping.dto.response.ShipmentEventResponse;
import com.dgl.shipping.dto.response.ShipmentResponse;
import com.dgl.shipping.dto.response.TrackingResponse;
import org.springframework.stereotype.Component;

import java.util.Collections;
import java.util.List;

@Component
public class ShipmentResponseMapper {

    public ShipmentResponse toResponse(Shipment shipment) {
        if (shipment == null) {
            return null;
        }

        List<ShipmentEventResponse> eventResponses = shipment.getEvents() != null
                ? shipment.getEvents().stream().map(this::toEventResponse).toList()
                : Collections.emptyList();

        return new ShipmentResponse(
                shipment.getId(),
                shipment.getOrderId(),
                shipment.getCustomerId(),
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

    public ShipmentEventResponse toEventResponse(ShipmentEvent event) {
        if (event == null) {
            return null;
        }

        return new ShipmentEventResponse(
                event.getId(),
                event.getStatus(),
                event.getDescription(),
                event.getLocation(),
                event.getEventTime()
        );
    }

    public TrackingResponse toTrackingResponse(Shipment shipment) {
        if (shipment == null) {
            return null;
        }

        List<ShipmentEventResponse> eventResponses = shipment.getEvents() != null
                ? shipment.getEvents().stream().map(this::toEventResponse).toList()
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
}
