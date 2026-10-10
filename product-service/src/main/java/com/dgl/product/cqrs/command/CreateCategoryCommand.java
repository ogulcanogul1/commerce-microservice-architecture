package com.dgl.product.cqrs.command;

import com.dgl.product.cqrs.Command;
import com.dgl.product.dto.request.CreateCategoryRequest;
import com.dgl.product.dto.response.CategoryResponse;

public record CreateCategoryCommand(CreateCategoryRequest request) implements Command<CategoryResponse> {
}
