package com.dgl.product.cqrs.command;

import com.dgl.product.cqrs.Command;
import com.dgl.product.dto.request.UpdateCategoryRequest;
import com.dgl.product.dto.response.CategoryResponse;

import java.util.UUID;

public record UpdateCategoryCommand(UUID id, UpdateCategoryRequest request) implements Command<CategoryResponse> {
}
