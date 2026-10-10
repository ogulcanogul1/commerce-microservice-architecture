package com.dgl.customer.cqrs.command;

import com.dgl.customer.cqrs.Command;
import com.dgl.customer.dto.response.AddressResponse;

import java.util.UUID;

public record SetDefaultAddressCommand(UUID customerId, UUID addressId) implements Command<AddressResponse> {
}
