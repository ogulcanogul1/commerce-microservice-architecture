package com.dgl.product.cqrs.query;

import com.dgl.product.cqrs.Query;
import com.dgl.product.dto.response.CategoryResponse;

public record GetCategoryBySlugQuery(String slug) implements Query<CategoryResponse> {
}
