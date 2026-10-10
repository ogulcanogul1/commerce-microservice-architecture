package com.dgl.customer.cqrs.command;

import com.dgl.customer.cqrs.Command;
import com.dgl.customer.dto.request.CreateCustomerRequest;
import com.dgl.customer.dto.response.CustomerResponse;

public record CreateCustomerCommand(CreateCustomerRequest request) implements Command<CustomerResponse> {
}
