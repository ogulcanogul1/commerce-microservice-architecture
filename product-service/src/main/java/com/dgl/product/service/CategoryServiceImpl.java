package com.dgl.product.service;

import com.dgl.product.cqrs.CommandBus;
import com.dgl.product.cqrs.QueryBus;
import com.dgl.product.cqrs.command.CreateCategoryCommand;
import com.dgl.product.cqrs.command.DeleteCategoryCommand;
import com.dgl.product.cqrs.command.UpdateCategoryCommand;
import com.dgl.product.cqrs.query.GetAllCategoriesQuery;
import com.dgl.product.cqrs.query.GetCategoryByIdQuery;
import com.dgl.product.cqrs.query.GetCategoryBySlugQuery;
import com.dgl.product.dto.request.CreateCategoryRequest;
import com.dgl.product.dto.request.UpdateCategoryRequest;
import com.dgl.product.dto.response.CategoryResponse;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;

import java.util.List;
import java.util.UUID;

@Slf4j
@Service
@RequiredArgsConstructor
public class CategoryServiceImpl implements CategoryService {

    private final CommandBus commandBus;
    private final QueryBus queryBus;

    @Override
    public CategoryResponse createCategory(CreateCategoryRequest request) {
        return commandBus.execute(new CreateCategoryCommand(request));
    }

    @Override
    public CategoryResponse updateCategory(UUID id, UpdateCategoryRequest request) {
        return commandBus.execute(new UpdateCategoryCommand(id, request));
    }

    @Override
    public CategoryResponse getCategoryById(UUID id) {
        return queryBus.execute(new GetCategoryByIdQuery(id));
    }

    @Override
    public CategoryResponse getCategoryBySlug(String slug) {
        return queryBus.execute(new GetCategoryBySlugQuery(slug));
    }

    @Override
    public List<CategoryResponse> getAllCategories() {
        return queryBus.execute(new GetAllCategoriesQuery());
    }

    @Override
    public void deleteCategory(UUID id) {
        commandBus.execute(new DeleteCategoryCommand(id));
    }
}
