package com.dgl.customer.cqrs.command;

import com.dgl.customer.cqrs.Command;
import com.dgl.customer.dto.request.CreateAddressRequest;
import com.dgl.customer.dto.response.AddressResponse;

import java.util.UUID;

public record AddAddressCommand(UUID customerId, CreateAddressRequest request) implements Command<AddressResponse> {
}
