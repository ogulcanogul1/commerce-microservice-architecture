package com.dgl.customer.controller;

import com.dgl.customer.cqrs.CommandBus;
import com.dgl.customer.cqrs.QueryBus;
import com.dgl.customer.cqrs.command.AddAddressCommand;
import com.dgl.customer.cqrs.command.DeleteAddressCommand;
import com.dgl.customer.cqrs.command.SetDefaultAddressCommand;
import com.dgl.customer.cqrs.query.GetCustomerAddressesQuery;
import com.dgl.customer.cqrs.query.GetDefaultAddressQuery;
import com.dgl.customer.dto.request.CreateAddressRequest;
import com.dgl.customer.dto.response.AddressResponse;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.List;
import java.util.UUID;

@RestController
@RequestMapping("/api/v1/customers/{customerId}/addresses")
@RequiredArgsConstructor
public class AddressController {

    private final CommandBus commandBus;
    private final QueryBus queryBus;

    @PostMapping
    public ResponseEntity<AddressResponse> addAddress(
            @PathVariable UUID customerId,
            @Valid @RequestBody CreateAddressRequest request) {
        AddressResponse response = commandBus.execute(new AddAddressCommand(customerId, request));
        return ResponseEntity.status(HttpStatus.CREATED).body(response);
    }

    @GetMapping
    public ResponseEntity<List<AddressResponse>> getCustomerAddresses(@PathVariable UUID customerId) {
        return ResponseEntity.ok(queryBus.execute(new GetCustomerAddressesQuery(customerId)));
    }

    @GetMapping("/default")
    public ResponseEntity<AddressResponse> getDefaultAddress(@PathVariable UUID customerId) {
        return ResponseEntity.ok(queryBus.execute(new GetDefaultAddressQuery(customerId)));
    }

    @PutMapping("/{addressId}/default")
    public ResponseEntity<AddressResponse> setDefaultAddress(
            @PathVariable UUID customerId,
            @PathVariable UUID addressId) {
        return ResponseEntity.ok(commandBus.execute(new SetDefaultAddressCommand(customerId, addressId)));
    }

    @DeleteMapping("/{addressId}")
    public ResponseEntity<Void> deleteAddress(
            @PathVariable UUID customerId,
            @PathVariable UUID addressId) {
        commandBus.execute(new DeleteAddressCommand(customerId, addressId));
        return ResponseEntity.noContent().build();
    }
}
