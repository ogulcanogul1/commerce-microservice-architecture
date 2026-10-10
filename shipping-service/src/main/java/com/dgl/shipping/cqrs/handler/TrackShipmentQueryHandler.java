package com.dgl.shipping.cqrs.handler;

import com.dgl.shipping.cqrs.QueryHandler;
import com.dgl.shipping.cqrs.mapper.ShipmentResponseMapper;
import com.dgl.shipping.cqrs.query.TrackShipmentQuery;
import com.dgl.shipping.domain.Shipment;
import com.dgl.shipping.dto.response.TrackingResponse;
import com.dgl.shipping.exception.ShipmentNotFoundException;
import com.dgl.shipping.repository.ShipmentRepository;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;

@Component
@RequiredArgsConstructor
public class TrackShipmentQueryHandler implements QueryHandler<TrackShipmentQuery, TrackingResponse> {

    private final ShipmentRepository shipmentRepository;
    private final ShipmentResponseMapper responseMapper;

    @Override
    @Transactional(readOnly = true)
    public TrackingResponse handle(TrackShipmentQuery query) {
        Shipment shipment = shipmentRepository.findByTrackingNumber(query.trackingNumber())
                .orElseThrow(() -> new ShipmentNotFoundException("Shipment not found with tracking number: " + query.trackingNumber()));
        return responseMapper.toTrackingResponse(shipment);
    }
}
