package com.dgl.customer.cqrs.handler;

import com.dgl.customer.cqrs.CommandHandler;
import com.dgl.customer.cqrs.command.AddAddressCommand;
import com.dgl.customer.cqrs.mapper.CustomerResponseMapper;
import com.dgl.customer.domain.Customer;
import com.dgl.customer.domain.CustomerAddress;
import com.dgl.customer.dto.request.CreateAddressRequest;
import com.dgl.customer.dto.response.AddressResponse;
import com.dgl.customer.exception.CustomerNotFoundException;
import com.dgl.customer.repository.CustomerAddressRepository;
import com.dgl.customer.repository.CustomerRepository;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;

import java.util.List;
import java.util.UUID;

@Component
@RequiredArgsConstructor
public class AddAddressCommandHandler implements CommandHandler<AddAddressCommand, AddressResponse> {

    private final CustomerRepository customerRepository;
    private final CustomerAddressRepository addressRepository;
    private final CustomerResponseMapper responseMapper;

    @Override
    @Transactional
    public AddressResponse handle(AddAddressCommand command) {
        UUID customerId = command.customerId();
        CreateAddressRequest request = command.request();

        Customer customer = customerRepository.findById(customerId)
                .orElseThrow(() -> new CustomerNotFoundException(customerId));

        List<CustomerAddress> existingAddresses = addressRepository.findByCustomerId(customerId);
        boolean isFirstAddress = existingAddresses.isEmpty();
        boolean shouldBeDefault = request.isDefault() || isFirstAddress;

        if (shouldBeDefault && !existingAddresses.isEmpty()) {
            for (CustomerAddress addr : existingAddresses) {
                if (addr.isDefault()) {
                    addr.setDefault(false);
                }
            }
        }

        CustomerAddress address = CustomerAddress.builder()
                .customer(customer)
                .title(request.title())
                .addressLine1(request.addressLine1())
                .addressLine2(request.addressLine2())
                .city(request.city())
                .district(request.district())
                .postalCode(request.postalCode())
                .country(request.country() != null ? request.country() : "Türkiye")
                .isDefault(shouldBeDefault)
                .build();

        CustomerAddress saved = addressRepository.save(address);
        return responseMapper.toAddressResponse(saved);
    }
}
