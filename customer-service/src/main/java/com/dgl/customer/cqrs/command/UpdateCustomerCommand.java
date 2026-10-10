package com.dgl.customer.cqrs.command;

import com.dgl.customer.cqrs.Command;
import com.dgl.customer.dto.request.UpdateCustomerRequest;
import com.dgl.customer.dto.response.CustomerResponse;

import java.util.UUID;

public record UpdateCustomerCommand(UUID id, UpdateCustomerRequest request) implements Command<CustomerResponse> {
}
