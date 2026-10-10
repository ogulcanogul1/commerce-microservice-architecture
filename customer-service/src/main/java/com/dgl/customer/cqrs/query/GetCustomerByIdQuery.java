package com.dgl.customer.cqrs.query;

import com.dgl.customer.cqrs.Query;
import com.dgl.customer.dto.response.CustomerResponse;

import java.util.UUID;

public record GetCustomerByIdQuery(UUID id) implements Query<CustomerResponse> {
}
