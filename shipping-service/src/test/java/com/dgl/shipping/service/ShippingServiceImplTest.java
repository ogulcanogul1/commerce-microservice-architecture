package com.dgl.shipping.service;

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
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.*;

@ExtendWith(MockitoExtension.class)
class ShippingServiceImplTest {

    @Mock
    private CommandBus commandBus;

    @Mock
    private QueryBus queryBus;

    @InjectMocks
    private ShippingServiceImpl shippingService;

    @Test
    @DisplayName("createShipment: Should delegate to command bus")
    void createShipment_shouldDelegate() {
        CreateShipmentRequest request = new CreateShipmentRequest(UUID.randomUUID(), Carrier.YURTICI, "Name", "Addr");
        ShipmentResponse mockResponse = mock(ShipmentResponse.class);
        when(commandBus.execute(any(CreateShipmentCommand.class))).thenReturn(mockResponse);

        ShipmentResponse actual = shippingService.createShipment(request);

        assertThat(actual).isSameAs(mockResponse);
        verify(commandBus).execute(new CreateShipmentCommand(request));
    }

    @Test
    @DisplayName("getShipmentById: Should delegate to query bus")
    void getShipmentById_shouldDelegate() {
        UUID id = UUID.randomUUID();
        ShipmentResponse mockResponse = mock(ShipmentResponse.class);
        when(queryBus.execute(any(GetShipmentByIdQuery.class))).thenReturn(mockResponse);

        ShipmentResponse actual = shippingService.getShipmentById(id);

        assertThat(actual).isSameAs(mockResponse);
        verify(queryBus).execute(new GetShipmentByIdQuery(id));
    }

    @Test
    @DisplayName("getShipmentByOrderId: Should delegate to query bus")
    void getShipmentByOrderId_shouldDelegate() {
        UUID orderId = UUID.randomUUID();
        ShipmentResponse mockResponse = mock(ShipmentResponse.class);
        when(queryBus.execute(any(GetShipmentByOrderIdQuery.class))).thenReturn(mockResponse);

        ShipmentResponse actual = shippingService.getShipmentByOrderId(orderId);

        assertThat(actual).isSameAs(mockResponse);
        verify(queryBus).execute(new GetShipmentByOrderIdQuery(orderId));
    }

    @Test
    @DisplayName("trackShipment: Should delegate to query bus")
    void trackShipment_shouldDelegate() {
        TrackingResponse mockResponse = mock(TrackingResponse.class);
        when(queryBus.execute(any(TrackShipmentQuery.class))).thenReturn(mockResponse);

        TrackingResponse actual = shippingService.trackShipment("TRK-123");

        assertThat(actual).isSameAs(mockResponse);
        verify(queryBus).execute(new TrackShipmentQuery("TRK-123"));
    }

    @Test
    @DisplayName("updateShipmentStatus: Should delegate to command bus")
    void updateShipmentStatus_shouldDelegate() {
        UUID id = UUID.randomUUID();
        UpdateShipmentStatusRequest request = new UpdateShipmentStatusRequest(ShipmentStatus.IN_TRANSIT, "On way", "City");
        ShipmentResponse mockResponse = mock(ShipmentResponse.class);
        when(commandBus.execute(any(UpdateShipmentStatusCommand.class))).thenReturn(mockResponse);

        ShipmentResponse actual = shippingService.updateShipmentStatus(id, request);

        assertThat(actual).isSameAs(mockResponse);
        verify(commandBus).execute(new UpdateShipmentStatusCommand(id, request));
    }

    @Test
    @DisplayName("cancelShipment: Should delegate to command bus")
    void cancelShipment_shouldDelegate() {
        UUID id = UUID.randomUUID();
        ShipmentResponse mockResponse = mock(ShipmentResponse.class);
        when(commandBus.execute(any(CancelShipmentCommand.class))).thenReturn(mockResponse);

        ShipmentResponse actual = shippingService.cancelShipment(id, "Cancelled");

        assertThat(actual).isSameAs(mockResponse);
        verify(commandBus).execute(new CancelShipmentCommand(id, "Cancelled"));
    }
}
