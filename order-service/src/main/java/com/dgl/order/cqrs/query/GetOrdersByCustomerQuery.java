package com.dgl.order.cqrs.query;

import com.dgl.order.cqrs.Query;
import com.dgl.order.dto.response.OrderResponse;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;

import java.util.UUID;

/**
 * Query to retrieve paginated orders placed by a specific customer.
 */
public record GetOrdersByCustomerQuery(
        UUID customerId,
        Pageable pageable
) implements Query<Page<OrderResponse>> {
}
