package com.dgl.e2e.dto;

import java.math.BigDecimal;

public record CreateOrderItemRequest(
        String sku,
        String productName,
        BigDecimal unitPrice,
        int quantity
) {}
