package com.dgl.product.cqrs.query;

import com.dgl.product.cqrs.Query;
import com.dgl.product.dto.response.ProductResponse;

public record GetProductBySkuQuery(String sku) implements Query<ProductResponse> {
}
