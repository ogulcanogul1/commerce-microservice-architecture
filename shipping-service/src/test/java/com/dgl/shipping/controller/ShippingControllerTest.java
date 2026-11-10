package com.dgl.shipping.controller;

import com.dgl.shipping.cqrs.CommandBus;
import com.dgl.shipping.cqrs.QueryBus;
import com.dgl.shipping.cqrs.command.CancelShipmentCommand;
import com.dgl.shipping.cqrs.command.CreateShipmentCommand;
import com.dgl.shipping.cqrs.command.UpdateShipmentStatusCommand;
import com.dgl.shipping.cqrs.query.GetShipmentByIdQuery;
import com.dgl.shipping.cqrs.query.GetShipmentByOrderIdQuery;
import com.dgl.shipping.cqrs.query.TrackShipmentQuery;
import com.dgl.shipping.domain.Carrier;
import com.dgl.shipping.domain.ShipmentStatus;
import com.dgl.shipping.dto.request.CreateShipmentRequest;
import com.dgl.shipping.dto.request.UpdateShipmentStatusRequest;
import com.dgl.shipping.dto.response.ShipmentResponse;
import com.dgl.shipping.dto.response.TrackingResponse;
import com.dgl.shipping.exception.AccessDeniedException;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;

import java.time.Instant;
import java.util.List;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.*;

@ExtendWith(MockitoExtension.class)
class ShippingControllerTest {

    @Mock
    private CommandBus commandBus;

    @Mock
    private QueryBus queryBus;

    @InjectMocks
    private ShippingController controller;

    private UUID shipmentId;
    private UUID customerId;
    private ShipmentResponse mockShipmentResponse;
    private TrackingResponse mockTrackingResponse;

    @BeforeEach
    void setUp() {
        shipmentId = UUID.randomUUID();
        customerId = UUID.randomUUID();
        mockShipmentResponse = new ShipmentResponse(
                shipmentId,
                UUID.randomUUID(),
                customerId,
                "TRK-100",
                Carrier.YURTICI,
                ShipmentStatus.CREATED,
                "Ahmet",
                "Istanbul",
                Instant.now(),
                null,
                null,
                List.of(),
                Instant.now(),
                Instant.now()
        );
        mockTrackingResponse = new TrackingResponse(
                "TRK-100",
                Carrier.YURTICI,
                ShipmentStatus.CREATED,
                Instant.now(),
                null,
                List.of()
        );
    }

    @Test
    @DisplayName("createShipment: Should dispatch command and return 201 Created")
    void createShipment_shouldReturn201() {
        CreateShipmentRequest request = new CreateShipmentRequest(UUID.randomUUID(), customerId, Carrier.YURTICI, "Ahmet", "Istanbul");
        when(commandBus.execute(any(CreateShipmentCommand.class))).thenReturn(mockShipmentResponse);

        ResponseEntity<ShipmentResponse> response = controller.createShipment(request);

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.CREATED);
        assertThat(response.getBody()).isSameAs(mockShipmentResponse);
        verify(commandBus).execute(new CreateShipmentCommand(request));
    }

    @Test
    @DisplayName("getShipmentById: Should dispatch query and return 200 OK when authorized owner")
    void getShipmentById_shouldReturn200() {
        when(queryBus.execute(any(GetShipmentByIdQuery.class))).thenReturn(mockShipmentResponse);

        ResponseEntity<ShipmentResponse> response = controller.getShipmentById(
                shipmentId, customerId.toString(), "ROLE_CUSTOMER");

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(response.getBody()).isSameAs(mockShipmentResponse);
        verify(queryBus).execute(new GetShipmentByIdQuery(shipmentId));
    }

    @Test
    @DisplayName("getShipmentById: Should throw AccessDeniedException when caller is neither owner nor admin")
    void getShipmentById_shouldThrowAccessDeniedWhenNotOwner() {
        when(queryBus.execute(any(GetShipmentByIdQuery.class))).thenReturn(mockShipmentResponse);
        String attackerId = UUID.randomUUID().toString();

        assertThatThrownBy(() -> controller.getShipmentById(
                shipmentId, attackerId, "ROLE_CUSTOMER"))
                .isInstanceOf(AccessDeniedException.class)
                .hasMessageContaining("you do not have permission");
    }

    @Test
    @DisplayName("getShipmentByOrderId: Should dispatch query and return 200 OK when owner")
    void getShipmentByOrderId_shouldReturn200() {
        UUID orderId = UUID.randomUUID();
        when(queryBus.execute(any(GetShipmentByOrderIdQuery.class))).thenReturn(mockShipmentResponse);

        ResponseEntity<ShipmentResponse> response = controller.getShipmentByOrderId(
                orderId, customerId.toString(), "ROLE_CUSTOMER");

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(response.getBody()).isSameAs(mockShipmentResponse);
        verify(queryBus).execute(new GetShipmentByOrderIdQuery(orderId));
    }

    @Test
    @DisplayName("trackShipment: Should dispatch query and return 200 OK")
    void trackShipment_shouldReturn200() {
        when(queryBus.execute(any(TrackShipmentQuery.class))).thenReturn(mockTrackingResponse);

        ResponseEntity<TrackingResponse> response = controller.trackShipment("TRK-100");

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(response.getBody()).isSameAs(mockTrackingResponse);
        verify(queryBus).execute(new TrackShipmentQuery("TRK-100"));
    }

    @Test
    @DisplayName("updateShipmentStatus: Should dispatch command and return 200 OK when caller is admin")
    void updateShipmentStatus_shouldReturn200ForAdmin() {
        UpdateShipmentStatusRequest request = new UpdateShipmentStatusRequest(ShipmentStatus.IN_TRANSIT, "Moving", "Ankara");
        when(commandBus.execute(any(UpdateShipmentStatusCommand.class))).thenReturn(mockShipmentResponse);

        ResponseEntity<ShipmentResponse> response = controller.updateShipmentStatus(
                shipmentId, request, "ROLE_ADMIN");

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(response.getBody()).isSameAs(mockShipmentResponse);
        verify(commandBus).execute(new UpdateShipmentStatusCommand(shipmentId, request));
    }

    @Test
    @DisplayName("updateShipmentStatus: Should throw AccessDeniedException when caller is not admin")
    void updateShipmentStatus_shouldThrowAccessDeniedWhenNotAdmin() {
        UpdateShipmentStatusRequest request = new UpdateShipmentStatusRequest(ShipmentStatus.IN_TRANSIT, "Moving", "Ankara");

        assertThatThrownBy(() -> controller.updateShipmentStatus(
                shipmentId, request, "ROLE_CUSTOMER"))
                .isInstanceOf(AccessDeniedException.class)
                .hasMessageContaining("only administrators may update shipment status directly");
    }

    @Test
    @DisplayName("cancelShipment: Should dispatch command and return 200 OK when owner")
    void cancelShipment_shouldReturn200() {
        when(queryBus.execute(any(GetShipmentByIdQuery.class))).thenReturn(mockShipmentResponse);
        when(commandBus.execute(any(CancelShipmentCommand.class))).thenReturn(mockShipmentResponse);

        ResponseEntity<ShipmentResponse> response = controller.cancelShipment(
                shipmentId, "User cancelled", customerId.toString(), "ROLE_CUSTOMER");

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(response.getBody()).isSameAs(mockShipmentResponse);
        verify(commandBus).execute(new CancelShipmentCommand(shipmentId, "User cancelled"));
    }

    @Test
    @DisplayName("cancelShipment: Should throw AccessDeniedException when caller is not owner")
    void cancelShipment_shouldThrowAccessDeniedWhenNotOwner() {
        when(queryBus.execute(any(GetShipmentByIdQuery.class))).thenReturn(mockShipmentResponse);
        String attackerId = UUID.randomUUID().toString();

        assertThatThrownBy(() -> controller.cancelShipment(
                shipmentId, "User cancelled", attackerId, "ROLE_CUSTOMER"))
                .isInstanceOf(AccessDeniedException.class)
                .hasMessageContaining("you do not have permission");
    }
}
