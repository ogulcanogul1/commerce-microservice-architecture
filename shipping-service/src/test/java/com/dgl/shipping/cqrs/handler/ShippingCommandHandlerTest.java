package com.dgl.shipping.cqrs.handler;

import com.dgl.shipping.cqrs.command.CancelShipmentCommand;
import com.dgl.shipping.cqrs.command.CreateShipmentCommand;
import com.dgl.shipping.cqrs.command.UpdateShipmentStatusCommand;
import com.dgl.shipping.cqrs.mapper.ShipmentResponseMapper;
import com.dgl.shipping.domain.Carrier;
import com.dgl.shipping.domain.Shipment;
import com.dgl.shipping.domain.ShipmentStatus;
import com.dgl.shipping.dto.request.CreateShipmentRequest;
import com.dgl.shipping.dto.request.UpdateShipmentStatusRequest;
import com.dgl.shipping.dto.response.ShipmentResponse;
import com.dgl.shipping.exception.InvalidShippingStateException;
import com.dgl.shipping.messaging.event.ShipmentCancelledPayload;
import com.dgl.shipping.messaging.event.ShipmentCreatedPayload;
import com.dgl.shipping.messaging.event.ShipmentDeliveredPayload;
import com.dgl.shipping.outbox.OutboxService;
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
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.ArgumentMatchers.isNull;
import static org.mockito.Mockito.*;

@ExtendWith(MockitoExtension.class)
class ShippingCommandHandlerTest {

    @Mock
    private ShipmentRepository shipmentRepository;

    @Mock
    private OutboxService outboxService;

    private final ShipmentResponseMapper responseMapper = new ShipmentResponseMapper();

    private CreateShipmentCommandHandler createShipmentHandler;
    private UpdateShipmentStatusCommandHandler updateStatusHandler;
    private CancelShipmentCommandHandler cancelShipmentHandler;

    private UUID shipmentId;
    private UUID orderId;
    private Shipment sampleShipment;

    @BeforeEach
    void setUp() {
        createShipmentHandler = new CreateShipmentCommandHandler(shipmentRepository, outboxService, responseMapper);
        updateStatusHandler = new UpdateShipmentStatusCommandHandler(shipmentRepository, outboxService, responseMapper);
        cancelShipmentHandler = new CancelShipmentCommandHandler(shipmentRepository, outboxService, responseMapper);

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
    @DisplayName("createShipment: Should generate tracking number, save shipment and emit ShipmentCreated outbox event")
    void createShipment_shouldSaveAndEmitOutboxEvent() {
        when(shipmentRepository.save(any(Shipment.class))).thenAnswer(i -> {
            Shipment s = i.getArgument(0);
            s.setId(shipmentId);
            return s;
        });

        CreateShipmentRequest request = new CreateShipmentRequest(
                orderId,
                Carrier.YURTICI,
                "Ahmet Yilmaz",
                "Bagdat Cad. No:1 Kadikoy Istanbul"
        );

        ShipmentResponse response = createShipmentHandler.handle(new CreateShipmentCommand(request));

        assertThat(response).isNotNull();
        assertThat(response.id()).isEqualTo(shipmentId);
        assertThat(response.status()).isEqualTo(ShipmentStatus.CREATED);
        assertThat(response.trackingNumber()).startsWith("TRK-");

        verify(outboxService).recordEvent(
                eq("Shipment"),
                eq(shipmentId.toString()),
                eq("ShipmentCreated"),
                isNull(),
                isNull(),
                any(ShipmentCreatedPayload.class)
        );
    }

    @Test
    @DisplayName("updateShipmentStatus: When marked DELIVERED, should set delivery time and emit ShipmentDelivered outbox event")
    void updateShipmentStatus_delivered_shouldEmitDeliveredOutboxEvent() {
        when(shipmentRepository.findById(shipmentId)).thenReturn(Optional.of(sampleShipment));

        UpdateShipmentStatusRequest request = new UpdateShipmentStatusRequest(
                ShipmentStatus.DELIVERED,
                "Delivered to recipient",
                "Istanbul"
        );

        ShipmentResponse response = updateStatusHandler.handle(new UpdateShipmentStatusCommand(shipmentId, request));

        assertThat(response.status()).isEqualTo(ShipmentStatus.DELIVERED);
        assertThat(sampleShipment.getActualDelivery()).isNotNull();

        verify(outboxService).recordEvent(
                eq("Shipment"),
                eq(shipmentId.toString()),
                eq("ShipmentDelivered"),
                isNull(),
                isNull(),
                any(ShipmentDeliveredPayload.class)
        );
    }

    @Test
    @DisplayName("updateShipmentStatus: Cannot update status of an already DELIVERED shipment")
    void updateShipmentStatus_alreadyDelivered_shouldThrowException() {
        sampleShipment.setStatus(ShipmentStatus.DELIVERED);
        when(shipmentRepository.findById(shipmentId)).thenReturn(Optional.of(sampleShipment));

        UpdateShipmentStatusRequest request = new UpdateShipmentStatusRequest(
                ShipmentStatus.IN_TRANSIT,
                "Invalid move",
                "Istanbul"
        );

        assertThatThrownBy(() -> updateStatusHandler.handle(new UpdateShipmentStatusCommand(shipmentId, request)))
                .isInstanceOf(InvalidShippingStateException.class)
                .hasMessageContaining("Cannot update status of a DELIVERED shipment");
    }

    @Test
    @DisplayName("cancelShipment: Should mark CANCELLED, add event and emit ShipmentCancelled outbox event")
    void cancelShipment_shouldCancelAndEmitOutboxEvent() {
        when(shipmentRepository.findById(shipmentId)).thenReturn(Optional.of(sampleShipment));

        ShipmentResponse response = cancelShipmentHandler.handle(new CancelShipmentCommand(shipmentId, "Order cancelled by user"));

        assertThat(response.status()).isEqualTo(ShipmentStatus.CANCELLED);
        assertThat(sampleShipment.getFailureReason()).isEqualTo("Order cancelled by user");

        verify(outboxService).recordEvent(
                eq("Shipment"),
                eq(shipmentId.toString()),
                eq("ShipmentCancelled"),
                isNull(),
                isNull(),
                any(ShipmentCancelledPayload.class)
        );
    }

    @Test
    @DisplayName("cancelShipment: Delivered shipment cannot be cancelled")
    void cancelShipment_deliveredShipment_shouldThrowException() {
        sampleShipment.setStatus(ShipmentStatus.DELIVERED);
        when(shipmentRepository.findById(shipmentId)).thenReturn(Optional.of(sampleShipment));

        assertThatThrownBy(() -> cancelShipmentHandler.handle(new CancelShipmentCommand(shipmentId, "Too late")))
                .isInstanceOf(InvalidShippingStateException.class)
                .hasMessageContaining("Delivered shipment cannot be cancelled");
    }
}
