package com.dgl.customer.cqrs.query;

import com.dgl.customer.cqrs.Query;
import com.dgl.customer.dto.response.AddressResponse;

import java.util.UUID;

public record GetDefaultAddressQuery(UUID customerId) implements Query<AddressResponse> {
}
