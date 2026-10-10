package com.dgl.customer.cqrs.handler;

import com.dgl.customer.cqrs.CommandHandler;
import com.dgl.customer.cqrs.command.DeleteAddressCommand;
import com.dgl.customer.domain.CustomerAddress;
import com.dgl.customer.exception.AddressNotFoundException;
import com.dgl.customer.exception.CustomerNotFoundException;
import com.dgl.customer.repository.CustomerAddressRepository;
import com.dgl.customer.repository.CustomerRepository;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;

import java.util.UUID;

@Component
@RequiredArgsConstructor
public class DeleteAddressCommandHandler implements CommandHandler<DeleteAddressCommand, Void> {

    private final CustomerRepository customerRepository;
    private final CustomerAddressRepository addressRepository;

    @Override
    @Transactional
    public Void handle(DeleteAddressCommand command) {
        UUID customerId = command.customerId();
        UUID addressId = command.addressId();

        if (!customerRepository.existsById(customerId)) {
            throw new CustomerNotFoundException(customerId);
        }

        CustomerAddress address = addressRepository.findById(addressId)
                .filter(a -> a.getCustomer().getId().equals(customerId))
                .orElseThrow(() -> new AddressNotFoundException(addressId));

        addressRepository.delete(address);
        return null;
    }
}
