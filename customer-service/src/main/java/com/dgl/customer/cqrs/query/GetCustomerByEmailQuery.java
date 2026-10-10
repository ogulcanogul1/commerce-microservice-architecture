package com.dgl.customer.cqrs.query;

import com.dgl.customer.cqrs.Query;
import com.dgl.customer.dto.response.CustomerResponse;

public record GetCustomerByEmailQuery(String email) implements Query<CustomerResponse> {
}
