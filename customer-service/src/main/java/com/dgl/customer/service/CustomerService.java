package com.dgl.customer.service;

import com.dgl.customer.dto.request.CreateCustomerRequest;
import com.dgl.customer.dto.request.UpdateCustomerRequest;
import com.dgl.customer.dto.request.UpdatePreferencesRequest;
import com.dgl.customer.dto.response.CustomerResponse;
import com.dgl.customer.dto.response.PreferencesResponse;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;

import java.util.UUID;

public interface CustomerService {

    CustomerResponse createCustomer(CreateCustomerRequest request);

    CustomerResponse updateCustomer(UUID id, UpdateCustomerRequest request);

    CustomerResponse getCustomerById(UUID id);

    CustomerResponse getCustomerByEmail(String email);

    Page<CustomerResponse> getAllCustomers(Pageable pageable);

    PreferencesResponse updatePreferences(UUID customerId, UpdatePreferencesRequest request);
}
