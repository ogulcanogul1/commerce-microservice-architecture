package com.dgl.product.dto.response;

import java.time.Instant;
import java.util.List;
import java.util.UUID;

public record CategoryResponse(
    UUID id,
    String name,
    String slug,
    String description,
    UUID parentId,
    List<CategoryResponse> subCategories,
    Instant createdAt,
    Instant updatedAt
) {}
