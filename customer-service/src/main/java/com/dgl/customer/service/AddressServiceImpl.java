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
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;

import java.util.List;
import java.util.UUID;

@Service
@RequiredArgsConstructor
public class AddressServiceImpl implements AddressService {

    private final CommandBus commandBus;
    private final QueryBus queryBus;

    @Override
    public AddressResponse addAddress(UUID customerId, CreateAddressRequest request) {
        return commandBus.execute(new AddAddressCommand(customerId, request));
    }

    @Override
    public List<AddressResponse> getCustomerAddresses(UUID customerId) {
        return queryBus.execute(new GetCustomerAddressesQuery(customerId));
    }

    @Override
    public AddressResponse getDefaultAddress(UUID customerId) {
        return queryBus.execute(new GetDefaultAddressQuery(customerId));
    }

    @Override
    public AddressResponse setDefaultAddress(UUID customerId, UUID addressId) {
        return commandBus.execute(new SetDefaultAddressCommand(customerId, addressId));
    }

    @Override
    public void deleteAddress(UUID customerId, UUID addressId) {
        commandBus.execute(new DeleteAddressCommand(customerId, addressId));
    }
}
