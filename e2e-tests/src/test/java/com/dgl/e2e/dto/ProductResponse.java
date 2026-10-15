package com.dgl.e2e.dto;

import java.math.BigDecimal;
import java.util.UUID;

public record ProductResponse(
        UUID id,
        String sku,
        String name,
        String slug,
        String description,
        UUID categoryId,
        BigDecimal basePrice,
        String currency
) {}
