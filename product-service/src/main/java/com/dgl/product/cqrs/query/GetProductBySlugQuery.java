package com.dgl.product.cqrs.query;

import com.dgl.product.cqrs.Query;
import com.dgl.product.dto.response.ProductResponse;

public record GetProductBySlugQuery(String slug) implements Query<ProductResponse> {
}
