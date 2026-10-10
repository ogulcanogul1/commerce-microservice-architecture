package com.dgl.shipping.cqrs.handler;

import com.dgl.shipping.cqrs.QueryHandler;
import com.dgl.shipping.cqrs.mapper.ShipmentResponseMapper;
import com.dgl.shipping.cqrs.query.GetShipmentByOrderIdQuery;
import com.dgl.shipping.domain.Shipment;
import com.dgl.shipping.dto.response.ShipmentResponse;
import com.dgl.shipping.exception.ShipmentNotFoundException;
import com.dgl.shipping.repository.ShipmentRepository;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;

@Component
@RequiredArgsConstructor
public class GetShipmentByOrderIdQueryHandler implements QueryHandler<GetShipmentByOrderIdQuery, ShipmentResponse> {

    private final ShipmentRepository shipmentRepository;
    private final ShipmentResponseMapper responseMapper;

    @Override
    @Transactional(readOnly = true)
    public ShipmentResponse handle(GetShipmentByOrderIdQuery query) {
        Shipment shipment = shipmentRepository.findByOrderId(query.orderId())
                .orElseThrow(() -> new ShipmentNotFoundException("Shipment not found for order: " + query.orderId()));
        return responseMapper.toResponse(shipment);
    }
}
