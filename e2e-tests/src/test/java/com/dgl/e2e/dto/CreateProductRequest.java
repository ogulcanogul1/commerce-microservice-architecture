package com.dgl.e2e.dto;

import java.math.BigDecimal;
import java.util.UUID;

public record CreateProductRequest(
        String sku,
        String name,
        String description,
        UUID categoryId,
        BigDecimal basePrice,
        String currency
) {}
