package com.dgl.customer.controller;

import com.dgl.customer.cqrs.CommandBus;
import com.dgl.customer.cqrs.QueryBus;
import com.dgl.customer.cqrs.command.AddAddressCommand;
import com.dgl.customer.cqrs.command.DeleteAddressCommand;
import com.dgl.customer.cqrs.command.SetDefaultAddressCommand;
import com.dgl.customer.cqrs.query.GetCustomerAddressesQuery;
import com.dgl.customer.cqrs.query.GetDefaultAddressQuery;
import com.dgl.customer.dto.request.CreateAddressRequest;
import com.dgl.customer.dto.response.AddressResponse;
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
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.*;

@ExtendWith(MockitoExtension.class)
class AddressControllerTest {

    @Mock
    private CommandBus commandBus;

    @Mock
    private QueryBus queryBus;

    @InjectMocks
    private AddressController controller;

    private UUID customerId;
    private UUID addressId;
    private AddressResponse mockAddressResponse;

    @BeforeEach
    void setUp() {
        customerId = UUID.randomUUID();
        addressId = UUID.randomUUID();
        mockAddressResponse = new AddressResponse(
                addressId,
                customerId,
                "Home",
                "Line 1",
                null,
                "Istanbul",
                "Kadikoy",
                "34000",
                "TR",
                true,
                Instant.now(),
                Instant.now()
        );
    }

    @Test
    @DisplayName("addAddress: Should dispatch command and return 201 Created")
    void addAddress_shouldReturn201() {
        CreateAddressRequest request = new CreateAddressRequest("Home", "Line 1", null, "Istanbul", "Kadikoy", "34000", "TR", true);
        when(commandBus.execute(any(AddAddressCommand.class))).thenReturn(mockAddressResponse);

        ResponseEntity<AddressResponse> response = controller.addAddress(customerId, request);

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.CREATED);
        assertThat(response.getBody()).isSameAs(mockAddressResponse);
        verify(commandBus).execute(new AddAddressCommand(customerId, request));
    }

    @Test
    @DisplayName("getCustomerAddresses: Should dispatch query and return 200 OK")
    void getCustomerAddresses_shouldReturn200() {
        when(queryBus.execute(any(GetCustomerAddressesQuery.class))).thenReturn(List.of(mockAddressResponse));

        ResponseEntity<List<AddressResponse>> response = controller.getCustomerAddresses(customerId);

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(response.getBody()).hasSize(1);
        verify(queryBus).execute(new GetCustomerAddressesQuery(customerId));
    }

    @Test
    @DisplayName("getDefaultAddress: Should dispatch query and return 200 OK")
    void getDefaultAddress_shouldReturn200() {
        when(queryBus.execute(any(GetDefaultAddressQuery.class))).thenReturn(mockAddressResponse);

        ResponseEntity<AddressResponse> response = controller.getDefaultAddress(customerId);

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(response.getBody()).isSameAs(mockAddressResponse);
        verify(queryBus).execute(new GetDefaultAddressQuery(customerId));
    }

    @Test
    @DisplayName("setDefaultAddress: Should dispatch command and return 200 OK")
    void setDefaultAddress_shouldReturn200() {
        when(commandBus.execute(any(SetDefaultAddressCommand.class))).thenReturn(mockAddressResponse);

        ResponseEntity<AddressResponse> response = controller.setDefaultAddress(customerId, addressId);

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(response.getBody()).isSameAs(mockAddressResponse);
        verify(commandBus).execute(new SetDefaultAddressCommand(customerId, addressId));
    }

    @Test
    @DisplayName("deleteAddress: Should dispatch command and return 204 No Content")
    void deleteAddress_shouldReturn204() {
        ResponseEntity<Void> response = controller.deleteAddress(customerId, addressId);

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.NO_CONTENT);
        verify(commandBus).execute(new DeleteAddressCommand(customerId, addressId));
    }
}
