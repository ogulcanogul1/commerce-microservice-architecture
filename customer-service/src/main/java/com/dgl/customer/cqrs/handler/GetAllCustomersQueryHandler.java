package com.dgl.customer.cqrs.handler;

import com.dgl.customer.cqrs.QueryHandler;
import com.dgl.customer.cqrs.mapper.CustomerResponseMapper;
import com.dgl.customer.cqrs.query.GetAllCustomersQuery;
import com.dgl.customer.dto.response.CustomerResponse;
import com.dgl.customer.repository.CustomerRepository;
import lombok.RequiredArgsConstructor;
import org.springframework.data.domain.Page;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;

@Component
@RequiredArgsConstructor
public class GetAllCustomersQueryHandler implements QueryHandler<GetAllCustomersQuery, Page<CustomerResponse>> {

    private final CustomerRepository customerRepository;
    private final CustomerResponseMapper responseMapper;

    @Override
    @Transactional(readOnly = true)
    public Page<CustomerResponse> handle(GetAllCustomersQuery query) {
        return customerRepository.findAll(query.pageable())
                .map(responseMapper::toCustomerResponse);
    }
}
