package com.dgl.product.cqrs.query;

import com.dgl.product.cqrs.Query;
import com.dgl.product.dto.response.CategoryResponse;

import java.util.List;

public record GetAllCategoriesQuery() implements Query<List<CategoryResponse>> {
}
