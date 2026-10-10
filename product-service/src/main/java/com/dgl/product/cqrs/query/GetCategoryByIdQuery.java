package com.dgl.product.cqrs.query;

import com.dgl.product.cqrs.Query;
import com.dgl.product.dto.response.CategoryResponse;

import java.util.UUID;

public record GetCategoryByIdQuery(UUID id) implements Query<CategoryResponse> {
}
