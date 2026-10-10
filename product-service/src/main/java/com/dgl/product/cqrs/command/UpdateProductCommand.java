package com.dgl.product.cqrs.command;

import com.dgl.product.cqrs.Command;
import com.dgl.product.dto.request.UpdateProductRequest;
import com.dgl.product.dto.response.ProductResponse;

import java.util.UUID;

public record UpdateProductCommand(UUID id, UpdateProductRequest request) implements Command<ProductResponse> {
}
