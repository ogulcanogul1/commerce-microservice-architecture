package com.dgl.product.cqrs.query;

import com.dgl.product.cqrs.Query;
import com.dgl.product.dto.response.ProductResponse;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;

public record GetAllProductsQuery(Pageable pageable) implements Query<Page<ProductResponse>> {
}
