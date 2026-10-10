package com.dgl.customer.cqrs.query;

import com.dgl.customer.cqrs.Query;
import com.dgl.customer.dto.response.AddressResponse;

import java.util.List;
import java.util.UUID;

public record GetCustomerAddressesQuery(UUID customerId) implements Query<List<AddressResponse>> {
}
