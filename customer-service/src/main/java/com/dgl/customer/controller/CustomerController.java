package com.dgl.customer.controller;

import com.dgl.customer.dto.request.CreateCustomerRequest;
import com.dgl.customer.dto.request.UpdateCustomerRequest;
import com.dgl.customer.dto.request.UpdatePreferencesRequest;
import com.dgl.customer.dto.response.CustomerResponse;
import com.dgl.customer.dto.response.PreferencesResponse;
import com.dgl.customer.service.CustomerService;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.web.PageableDefault;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.util.UUID;

@RestController
@RequestMapping("/api/v1/customers")
@RequiredArgsConstructor
public class CustomerController {

    private final CustomerService customerService;

    @PostMapping
    public ResponseEntity<CustomerResponse> createCustomer(@Valid @RequestBody CreateCustomerRequest request) {
        CustomerResponse response = customerService.createCustomer(request);
        return ResponseEntity.status(HttpStatus.CREATED).body(response);
    }

    @GetMapping("/{id}")
    public ResponseEntity<CustomerResponse> getCustomerById(@PathVariable UUID id) {
        return ResponseEntity.ok(customerService.getCustomerById(id));
    }

    @GetMapping("/by-email")
    public ResponseEntity<CustomerResponse> getCustomerByEmail(@RequestParam String email) {
        return ResponseEntity.ok(customerService.getCustomerByEmail(email));
    }

    @GetMapping
    public ResponseEntity<Page<CustomerResponse>> getAllCustomers(@PageableDefault(size = 20) Pageable pageable) {
        return ResponseEntity.ok(customerService.getAllCustomers(pageable));
    }

    @PutMapping("/{id}")
    public ResponseEntity<CustomerResponse> updateCustomer(
            @PathVariable UUID id,
            @Valid @RequestBody UpdateCustomerRequest request) {
        return ResponseEntity.ok(customerService.updateCustomer(id, request));
    }

    @PutMapping("/{id}/preferences")
    public ResponseEntity<PreferencesResponse> updatePreferences(
            @PathVariable UUID id,
            @Valid @RequestBody UpdatePreferencesRequest request) {
        return ResponseEntity.ok(customerService.updatePreferences(id, request));
    }
}
