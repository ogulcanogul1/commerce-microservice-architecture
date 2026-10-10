package com.dgl.product.cqrs.query;

import com.dgl.product.cqrs.Query;
import com.dgl.product.dto.response.ProductResponse;

import java.util.UUID;

public record GetProductByIdQuery(UUID id) implements Query<ProductResponse> {
}
