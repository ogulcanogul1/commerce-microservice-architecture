package com.dgl.customer.service;

import com.dgl.customer.dto.request.CreateAddressRequest;
import com.dgl.customer.dto.response.AddressResponse;

import java.util.List;
import java.util.UUID;

public interface AddressService {

    AddressResponse addAddress(UUID customerId, CreateAddressRequest request);

    List<AddressResponse> getCustomerAddresses(UUID customerId);

    AddressResponse getDefaultAddress(UUID customerId);

    AddressResponse setDefaultAddress(UUID customerId, UUID addressId);

    void deleteAddress(UUID customerId, UUID addressId);
}
