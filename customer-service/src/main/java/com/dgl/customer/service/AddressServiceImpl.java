package com.dgl.customer.service;

import com.dgl.customer.domain.Customer;
import com.dgl.customer.domain.CustomerAddress;
import com.dgl.customer.dto.request.CreateAddressRequest;
import com.dgl.customer.dto.response.AddressResponse;
import com.dgl.customer.exception.AddressNotFoundException;
import com.dgl.customer.exception.CustomerNotFoundException;
import com.dgl.customer.repository.CustomerAddressRepository;
import com.dgl.customer.repository.CustomerRepository;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.List;
import java.util.UUID;

@Service
@RequiredArgsConstructor
@Transactional(readOnly = true)
public class AddressServiceImpl implements AddressService {

    private final CustomerRepository customerRepository;
    private final CustomerAddressRepository addressRepository;

    @Override
    @Transactional
    public AddressResponse addAddress(UUID customerId, CreateAddressRequest request) {
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
        return mapToResponse(saved);
    }

    @Override
    public List<AddressResponse> getCustomerAddresses(UUID customerId) {
        if (!customerRepository.existsById(customerId)) {
            throw new CustomerNotFoundException(customerId);
        }
        return addressRepository.findByCustomerId(customerId).stream()
                .map(this::mapToResponse)
                .toList();
    }

    @Override
    public AddressResponse getDefaultAddress(UUID customerId) {
        if (!customerRepository.existsById(customerId)) {
            throw new CustomerNotFoundException(customerId);
        }
        CustomerAddress address = addressRepository.findByCustomerId(customerId).stream()
                .filter(CustomerAddress::isDefault)
                .findFirst()
                .orElseThrow(() -> new AddressNotFoundException("Default address not found for customer: " + customerId));
        return mapToResponse(address);
    }

    @Override
    @Transactional
    public AddressResponse setDefaultAddress(UUID customerId, UUID addressId) {
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

        return mapToResponse(targetAddress);
    }

    @Override
    @Transactional
    public void deleteAddress(UUID customerId, UUID addressId) {
        if (!customerRepository.existsById(customerId)) {
            throw new CustomerNotFoundException(customerId);
        }
        CustomerAddress address = addressRepository.findById(addressId)
                .filter(a -> a.getCustomer().getId().equals(customerId))
                .orElseThrow(() -> new AddressNotFoundException(addressId));

        addressRepository.delete(address);
    }

    private AddressResponse mapToResponse(CustomerAddress address) {
        return new AddressResponse(
                address.getId(),
                address.getCustomer().getId(),
                address.getTitle(),
                address.getAddressLine1(),
                address.getAddressLine2(),
                address.getCity(),
                address.getDistrict(),
                address.getPostalCode(),
                address.getCountry(),
                address.isDefault(),
                address.getCreatedAt(),
                address.getUpdatedAt()
        );
    }
}
