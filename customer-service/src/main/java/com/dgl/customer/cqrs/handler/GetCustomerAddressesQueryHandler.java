package com.dgl.customer.cqrs.handler;

import com.dgl.customer.cqrs.QueryHandler;
import com.dgl.customer.cqrs.mapper.CustomerResponseMapper;
import com.dgl.customer.cqrs.query.GetCustomerAddressesQuery;
import com.dgl.customer.dto.response.AddressResponse;
import com.dgl.customer.exception.CustomerNotFoundException;
import com.dgl.customer.repository.CustomerAddressRepository;
import com.dgl.customer.repository.CustomerRepository;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;

import java.util.List;

@Component
@RequiredArgsConstructor
public class GetCustomerAddressesQueryHandler implements QueryHandler<GetCustomerAddressesQuery, List<AddressResponse>> {

    private final CustomerRepository customerRepository;
    private final CustomerAddressRepository addressRepository;
    private final CustomerResponseMapper responseMapper;

    @Override
    @Transactional(readOnly = true)
    public List<AddressResponse> handle(GetCustomerAddressesQuery query) {
        if (!customerRepository.existsById(query.customerId())) {
            throw new CustomerNotFoundException(query.customerId());
        }
        return addressRepository.findByCustomerId(query.customerId()).stream()
                .map(responseMapper::toAddressResponse)
                .toList();
    }
}
