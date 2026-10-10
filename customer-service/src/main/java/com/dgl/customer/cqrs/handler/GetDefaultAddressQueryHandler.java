package com.dgl.customer.cqrs.handler;

import com.dgl.customer.cqrs.QueryHandler;
import com.dgl.customer.cqrs.mapper.CustomerResponseMapper;
import com.dgl.customer.cqrs.query.GetDefaultAddressQuery;
import com.dgl.customer.domain.CustomerAddress;
import com.dgl.customer.dto.response.AddressResponse;
import com.dgl.customer.exception.AddressNotFoundException;
import com.dgl.customer.exception.CustomerNotFoundException;
import com.dgl.customer.repository.CustomerAddressRepository;
import com.dgl.customer.repository.CustomerRepository;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;

@Component
@RequiredArgsConstructor
public class GetDefaultAddressQueryHandler implements QueryHandler<GetDefaultAddressQuery, AddressResponse> {

    private final CustomerRepository customerRepository;
    private final CustomerAddressRepository addressRepository;
    private final CustomerResponseMapper responseMapper;

    @Override
    @Transactional(readOnly = true)
    public AddressResponse handle(GetDefaultAddressQuery query) {
        if (!customerRepository.existsById(query.customerId())) {
            throw new CustomerNotFoundException(query.customerId());
        }
        CustomerAddress address = addressRepository.findByCustomerId(query.customerId()).stream()
                .filter(CustomerAddress::isDefault)
                .findFirst()
                .orElseThrow(() -> new AddressNotFoundException("Default address not found for customer: " + query.customerId()));
        return responseMapper.toAddressResponse(address);
    }
}
