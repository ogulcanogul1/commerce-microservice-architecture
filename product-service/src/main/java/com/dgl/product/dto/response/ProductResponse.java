package com.dgl.product.dto.response;

import com.dgl.product.domain.ProductStatus;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.Map;
import java.util.UUID;

public record ProductResponse(
    UUID id,
    String sku,
    String name,
    String slug,
    String description,
    UUID categoryId,
    String categoryName,
    BigDecimal basePrice,
    String currency,
    ProductStatus status,
    Map<String, String> attributes,
    Instant createdAt,
    Instant updatedAt
) {}
