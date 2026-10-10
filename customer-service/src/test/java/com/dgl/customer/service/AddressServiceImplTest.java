package com.dgl.customer.service;

import com.dgl.customer.cqrs.CommandBus;
import com.dgl.customer.cqrs.QueryBus;
import com.dgl.customer.cqrs.command.AddAddressCommand;
import com.dgl.customer.cqrs.command.DeleteAddressCommand;
import com.dgl.customer.cqrs.command.SetDefaultAddressCommand;
import com.dgl.customer.cqrs.query.GetCustomerAddressesQuery;
import com.dgl.customer.cqrs.query.GetDefaultAddressQuery;
import com.dgl.customer.dto.request.CreateAddressRequest;
import com.dgl.customer.dto.response.AddressResponse;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import java.util.List;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.*;

@ExtendWith(MockitoExtension.class)
class AddressServiceImplTest {

    @Mock
    private CommandBus commandBus;

    @Mock
    private QueryBus queryBus;

    @InjectMocks
    private AddressServiceImpl addressService;

    @Test
    @DisplayName("addAddress: Should delegate to command bus")
    void addAddress_shouldDelegate() {
        UUID customerId = UUID.randomUUID();
        CreateAddressRequest request = new CreateAddressRequest("Home", "L1", null, "City", "Dist", "123", "TR", false);
        AddressResponse mockResponse = mock(AddressResponse.class);
        when(commandBus.execute(any(AddAddressCommand.class))).thenReturn(mockResponse);

        AddressResponse actual = addressService.addAddress(customerId, request);

        assertThat(actual).isSameAs(mockResponse);
        verify(commandBus).execute(new AddAddressCommand(customerId, request));
    }

    @Test
    @DisplayName("getCustomerAddresses: Should delegate to query bus")
    void getCustomerAddresses_shouldDelegate() {
        UUID customerId = UUID.randomUUID();
        List<AddressResponse> mockList = List.of();
        when(queryBus.execute(any(GetCustomerAddressesQuery.class))).thenReturn(mockList);

        List<AddressResponse> actual = addressService.getCustomerAddresses(customerId);

        assertThat(actual).isSameAs(mockList);
        verify(queryBus).execute(new GetCustomerAddressesQuery(customerId));
    }

    @Test
    @DisplayName("getDefaultAddress: Should delegate to query bus")
    void getDefaultAddress_shouldDelegate() {
        UUID customerId = UUID.randomUUID();
        AddressResponse mockResponse = mock(AddressResponse.class);
        when(queryBus.execute(any(GetDefaultAddressQuery.class))).thenReturn(mockResponse);

        AddressResponse actual = addressService.getDefaultAddress(customerId);

        assertThat(actual).isSameAs(mockResponse);
        verify(queryBus).execute(new GetDefaultAddressQuery(customerId));
    }

    @Test
    @DisplayName("setDefaultAddress: Should delegate to command bus")
    void setDefaultAddress_shouldDelegate() {
        UUID customerId = UUID.randomUUID();
        UUID addressId = UUID.randomUUID();
        AddressResponse mockResponse = mock(AddressResponse.class);
        when(commandBus.execute(any(SetDefaultAddressCommand.class))).thenReturn(mockResponse);

        AddressResponse actual = addressService.setDefaultAddress(customerId, addressId);

        assertThat(actual).isSameAs(mockResponse);
        verify(commandBus).execute(new SetDefaultAddressCommand(customerId, addressId));
    }

    @Test
    @DisplayName("deleteAddress: Should delegate to command bus")
    void deleteAddress_shouldDelegate() {
        UUID customerId = UUID.randomUUID();
        UUID addressId = UUID.randomUUID();

        addressService.deleteAddress(customerId, addressId);

        verify(commandBus).execute(new DeleteAddressCommand(customerId, addressId));
    }
}
