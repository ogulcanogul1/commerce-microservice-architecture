package com.dgl.customer.cqrs.query;

import com.dgl.customer.cqrs.Query;
import com.dgl.customer.dto.response.CustomerResponse;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;

public record GetAllCustomersQuery(Pageable pageable) implements Query<Page<CustomerResponse>> {
}
