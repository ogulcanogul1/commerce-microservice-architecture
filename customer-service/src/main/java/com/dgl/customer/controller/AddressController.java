package com.dgl.customer.controller;

import com.dgl.customer.dto.request.CreateAddressRequest;
import com.dgl.customer.dto.response.AddressResponse;
import com.dgl.customer.service.AddressService;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;
import java.util.UUID;

@RestController
@RequestMapping("/api/v1/customers/{customerId}/addresses")
@RequiredArgsConstructor
public class AddressController {

    private final AddressService addressService;

    @PostMapping
    public ResponseEntity<AddressResponse> addAddress(
            @PathVariable UUID customerId,
            @Valid @RequestBody CreateAddressRequest request) {
        AddressResponse response = addressService.addAddress(customerId, request);
        return ResponseEntity.status(HttpStatus.CREATED).body(response);
    }

    @GetMapping
    public ResponseEntity<List<AddressResponse>> getCustomerAddresses(@PathVariable UUID customerId) {
        return ResponseEntity.ok(addressService.getCustomerAddresses(customerId));
    }

    @GetMapping("/default")
    public ResponseEntity<AddressResponse> getDefaultAddress(@PathVariable UUID customerId) {
        return ResponseEntity.ok(addressService.getDefaultAddress(customerId));
    }

    @PutMapping("/{addressId}/default")
    public ResponseEntity<AddressResponse> setDefaultAddress(
            @PathVariable UUID customerId,
            @PathVariable UUID addressId) {
        return ResponseEntity.ok(addressService.setDefaultAddress(customerId, addressId));
    }

    @DeleteMapping("/{addressId}")
    public ResponseEntity<Void> deleteAddress(
            @PathVariable UUID customerId,
            @PathVariable UUID addressId) {
        addressService.deleteAddress(customerId, addressId);
        return ResponseEntity.noContent().build();
    }
}
