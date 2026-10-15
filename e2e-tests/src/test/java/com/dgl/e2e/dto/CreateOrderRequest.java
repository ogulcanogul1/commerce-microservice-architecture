package com.dgl.e2e.dto;

import java.util.List;
import java.util.UUID;

public record CreateOrderRequest(
        UUID customerId,
        List<CreateOrderItemRequest> items,
        String shippingAddress,
        String currency
) {}
