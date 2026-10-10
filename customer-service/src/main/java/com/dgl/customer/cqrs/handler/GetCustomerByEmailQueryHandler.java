package com.dgl.customer.cqrs.handler;

import com.dgl.customer.cqrs.QueryHandler;
import com.dgl.customer.cqrs.mapper.CustomerResponseMapper;
import com.dgl.customer.cqrs.query.GetCustomerByEmailQuery;
import com.dgl.customer.domain.Customer;
import com.dgl.customer.dto.response.CustomerResponse;
import com.dgl.customer.exception.CustomerNotFoundException;
import com.dgl.customer.repository.CustomerRepository;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;

@Component
@RequiredArgsConstructor
public class GetCustomerByEmailQueryHandler implements QueryHandler<GetCustomerByEmailQuery, CustomerResponse> {

    private final CustomerRepository customerRepository;
    private final CustomerResponseMapper responseMapper;

    @Override
    @Transactional(readOnly = true)
    public CustomerResponse handle(GetCustomerByEmailQuery query) {
        Customer customer = customerRepository.findByEmail(query.email().toLowerCase().trim())
                .orElseThrow(() -> new CustomerNotFoundException("Customer not found with email: " + query.email()));
        return responseMapper.toCustomerResponse(customer);
    }
}
