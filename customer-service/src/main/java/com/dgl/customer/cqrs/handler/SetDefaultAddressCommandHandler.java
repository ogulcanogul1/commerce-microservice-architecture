package com.dgl.customer.cqrs.handler;

import com.dgl.customer.cqrs.CommandHandler;
import com.dgl.customer.cqrs.command.SetDefaultAddressCommand;
import com.dgl.customer.cqrs.mapper.CustomerResponseMapper;
import com.dgl.customer.domain.CustomerAddress;
import com.dgl.customer.dto.response.AddressResponse;
import com.dgl.customer.exception.AddressNotFoundException;
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
public class SetDefaultAddressCommandHandler implements CommandHandler<SetDefaultAddressCommand, AddressResponse> {

    private final CustomerRepository customerRepository;
    private final CustomerAddressRepository addressRepository;
    private final CustomerResponseMapper responseMapper;

    @Override
    @Transactional
    public AddressResponse handle(SetDefaultAddressCommand command) {
        UUID customerId = command.customerId();
        UUID addressId = command.addressId();

        if (!customerRepository.existsById(customerId)) {
            throw new CustomerNotFoundException(customerId);
        }

        List<CustomerAddress> addresses = addressRepository.findByCustomerId(customerId);
        CustomerAddress targetAddress = null;

        for (CustomerAddress addr : addresses) {
            if (addr.getId().equals(addressId)) {
                targetAddress = addr;
                addr.setDefault(true);
            } else if (addr.isDefault()) {
                addr.setDefault(false);
            }
        }

        if (targetAddress == null) {
            throw new AddressNotFoundException("Address " + addressId + " not found for customer " + customerId);
        }

        return responseMapper.toAddressResponse(targetAddress);
    }
}
