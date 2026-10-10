package com.dgl.product.cqrs.command;

import com.dgl.product.cqrs.Command;
import com.dgl.product.dto.request.CreateProductRequest;
import com.dgl.product.dto.response.ProductResponse;

public record CreateProductCommand(CreateProductRequest request) implements Command<ProductResponse> {
}
