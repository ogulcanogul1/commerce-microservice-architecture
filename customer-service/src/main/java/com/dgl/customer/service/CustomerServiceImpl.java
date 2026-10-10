package com.dgl.customer.service;

import com.dgl.customer.cqrs.CommandBus;
import com.dgl.customer.cqrs.QueryBus;
import com.dgl.customer.cqrs.command.CreateCustomerCommand;
import com.dgl.customer.cqrs.command.UpdateCustomerCommand;
import com.dgl.customer.cqrs.command.UpdatePreferencesCommand;
import com.dgl.customer.cqrs.query.GetAllCustomersQuery;
import com.dgl.customer.cqrs.query.GetCustomerByEmailQuery;
import com.dgl.customer.cqrs.query.GetCustomerByIdQuery;
import com.dgl.customer.dto.request.CreateCustomerRequest;
import com.dgl.customer.dto.request.UpdateCustomerRequest;
import com.dgl.customer.dto.request.UpdatePreferencesRequest;
import com.dgl.customer.dto.response.CustomerResponse;
import com.dgl.customer.dto.response.PreferencesResponse;
import lombok.RequiredArgsConstructor;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.stereotype.Service;

import java.util.UUID;

@Service
@RequiredArgsConstructor
public class CustomerServiceImpl implements CustomerService {

    private final CommandBus commandBus;
    private final QueryBus queryBus;

    @Override
    public CustomerResponse createCustomer(CreateCustomerRequest request) {
        return commandBus.execute(new CreateCustomerCommand(request));
    }

    @Override
    public CustomerResponse updateCustomer(UUID id, UpdateCustomerRequest request) {
        return commandBus.execute(new UpdateCustomerCommand(id, request));
    }

    @Override
    public CustomerResponse getCustomerById(UUID id) {
        return queryBus.execute(new GetCustomerByIdQuery(id));
    }

    @Override
    public CustomerResponse getCustomerByEmail(String email) {
        return queryBus.execute(new GetCustomerByEmailQuery(email));
    }

    @Override
    public Page<CustomerResponse> getAllCustomers(Pageable pageable) {
        return queryBus.execute(new GetAllCustomersQuery(pageable));
    }

    @Override
    public PreferencesResponse updatePreferences(UUID customerId, UpdatePreferencesRequest request) {
        return commandBus.execute(new UpdatePreferencesCommand(customerId, request));
    }
}
