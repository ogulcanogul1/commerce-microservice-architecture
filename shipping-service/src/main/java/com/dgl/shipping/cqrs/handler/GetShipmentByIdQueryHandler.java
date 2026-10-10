package com.dgl.shipping.cqrs.handler;

import com.dgl.shipping.cqrs.QueryHandler;
import com.dgl.shipping.cqrs.mapper.ShipmentResponseMapper;
import com.dgl.shipping.cqrs.query.GetShipmentByIdQuery;
import com.dgl.shipping.domain.Shipment;
import com.dgl.shipping.dto.response.ShipmentResponse;
import com.dgl.shipping.exception.ShipmentNotFoundException;
import com.dgl.shipping.repository.ShipmentRepository;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;

@Component
@RequiredArgsConstructor
public class GetShipmentByIdQueryHandler implements QueryHandler<GetShipmentByIdQuery, ShipmentResponse> {

    private final ShipmentRepository shipmentRepository;
    private final ShipmentResponseMapper responseMapper;

    @Override
    @Transactional(readOnly = true)
    public ShipmentResponse handle(GetShipmentByIdQuery query) {
        Shipment shipment = shipmentRepository.findById(query.id())
                .orElseThrow(() -> new ShipmentNotFoundException(query.id()));
        return responseMapper.toResponse(shipment);
    }
}
