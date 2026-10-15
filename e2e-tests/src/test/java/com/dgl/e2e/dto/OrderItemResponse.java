package com.dgl.e2e.dto;

import java.math.BigDecimal;
import java.util.UUID;

public record OrderItemResponse(
        UUID id,
        String sku,
        String productName,
        BigDecimal unitPrice,
        int quantity,
        BigDecimal totalPrice
) {}
