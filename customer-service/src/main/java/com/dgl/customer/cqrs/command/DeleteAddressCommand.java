package com.dgl.customer.cqrs.command;

import com.dgl.customer.cqrs.Command;

import java.util.UUID;

public record DeleteAddressCommand(UUID customerId, UUID addressId) implements Command<Void> {
}
