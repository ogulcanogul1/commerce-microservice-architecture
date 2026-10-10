package com.dgl.shipping.cqrs.handler;

import com.dgl.shipping.cqrs.mapper.ShipmentResponseMapper;
import com.dgl.shipping.cqrs.query.GetShipmentByIdQuery;
import com.dgl.shipping.cqrs.query.GetShipmentByOrderIdQuery;
import com.dgl.shipping.cqrs.query.TrackShipmentQuery;
import com.dgl.shipping.domain.Carrier;
import com.dgl.shipping.domain.Shipment;
import com.dgl.shipping.domain.ShipmentStatus;
import com.dgl.shipping.dto.response.ShipmentResponse;
import com.dgl.shipping.dto.response.TrackingResponse;
import com.dgl.shipping.exception.ShipmentNotFoundException;
import com.dgl.shipping.repository.ShipmentRepository;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import java.util.ArrayList;
import java.util.Optional;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class ShippingQueryHandlerTest {

    @Mock
    private ShipmentRepository shipmentRepository;

    private final ShipmentResponseMapper responseMapper = new ShipmentResponseMapper();

    private GetShipmentByIdQueryHandler getByIdHandler;
    private GetShipmentByOrderIdQueryHandler getByOrderIdHandler;
    private TrackShipmentQueryHandler trackHandler;

    private UUID shipmentId;
    private UUID orderId;
    private Shipment sampleShipment;

    @BeforeEach
    void setUp() {
        getByIdHandler = new GetShipmentByIdQueryHandler(shipmentRepository, responseMapper);
        getByOrderIdHandler = new GetShipmentByOrderIdQueryHandler(shipmentRepository, responseMapper);
        trackHandler = new TrackShipmentQueryHandler(shipmentRepository, responseMapper);

        shipmentId = UUID.randomUUID();
        orderId = UUID.randomUUID();

        sampleShipment = Shipment.builder()
                .id(shipmentId)
                .orderId(orderId)
                .trackingNumber("TRK-TEST123456")
                .carrier(Carrier.YURTICI)
                .status(ShipmentStatus.CREATED)
                .recipientName("Ahmet Yilmaz")
                .deliveryAddress("Bagdat Cad. No:1 Kadikoy Istanbul")
                .events(new ArrayList<>())
                .build();
    }

    @Test
    @DisplayName("getShipmentById: Should return shipment when found")
    void getShipmentById_found_shouldReturn() {
        when(shipmentRepository.findById(shipmentId)).thenReturn(Optional.of(sampleShipment));

        ShipmentResponse response = getByIdHandler.handle(new GetShipmentByIdQuery(shipmentId));

        assertThat(response).isNotNull();
        assertThat(response.id()).isEqualTo(shipmentId);
    }

    @Test
    @DisplayName("getShipmentById: Should throw ShipmentNotFoundException when not found")
    void getShipmentById_notFound_shouldThrow() {
        when(shipmentRepository.findById(shipmentId)).thenReturn(Optional.empty());

        assertThatThrownBy(() -> getByIdHandler.handle(new GetShipmentByIdQuery(shipmentId)))
                .isInstanceOf(ShipmentNotFoundException.class);
    }

    @Test
    @DisplayName("getShipmentByOrderId: Should return shipment when found")
    void getShipmentByOrderId_found_shouldReturn() {
        when(shipmentRepository.findByOrderId(orderId)).thenReturn(Optional.of(sampleShipment));

        ShipmentResponse response = getByOrderIdHandler.handle(new GetShipmentByOrderIdQuery(orderId));

        assertThat(response).isNotNull();
        assertThat(response.orderId()).isEqualTo(orderId);
    }

    @Test
    @DisplayName("trackShipment: Should return tracking response when tracking number exists")
    void trackShipment_found_shouldReturnTracking() {
        when(shipmentRepository.findByTrackingNumber("TRK-TEST123456")).thenReturn(Optional.of(sampleShipment));

        TrackingResponse response = trackHandler.handle(new TrackShipmentQuery("TRK-TEST123456"));

        assertThat(response).isNotNull();
        assertThat(response.trackingNumber()).isEqualTo("TRK-TEST123456");
        assertThat(response.carrier()).isEqualTo(Carrier.YURTICI);
        assertThat(response.currentStatus()).isEqualTo(ShipmentStatus.CREATED);
    }
}
