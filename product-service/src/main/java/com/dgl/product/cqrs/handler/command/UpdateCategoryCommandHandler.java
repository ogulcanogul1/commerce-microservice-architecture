package com.dgl.product.cqrs.handler.command;

import com.dgl.product.config.RedisConfig;
import com.dgl.product.cqrs.CommandHandler;
import com.dgl.product.cqrs.command.UpdateCategoryCommand;
import com.dgl.product.cqrs.mapper.CategoryResponseMapper;
import com.dgl.product.domain.Category;
import com.dgl.product.dto.request.UpdateCategoryRequest;
import com.dgl.product.dto.response.CategoryResponse;
import com.dgl.product.exception.CategoryAlreadyExistsException;
import com.dgl.product.exception.CategoryNotFoundException;
import com.dgl.product.repository.CategoryRepository;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.cache.annotation.CacheEvict;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;

import java.util.UUID;

@Slf4j
@Component
@RequiredArgsConstructor
public class UpdateCategoryCommandHandler implements CommandHandler<UpdateCategoryCommand, CategoryResponse> {

    private final CategoryRepository categoryRepository;
    private final CategoryResponseMapper categoryResponseMapper;

    @Override
    @Transactional
    @CacheEvict(value = RedisConfig.CATEGORIES_CACHE, allEntries = true)
    public CategoryResponse handle(UpdateCategoryCommand command) {
        UUID id = command.id();
        UpdateCategoryRequest request = command.request();

        Category category = categoryRepository.findById(id)
                .orElseThrow(() -> new CategoryNotFoundException(id));

        if (!category.getName().equalsIgnoreCase(request.name()) && categoryRepository.existsByName(request.name())) {
            throw new CategoryAlreadyExistsException("Category with name '" + request.name() + "' already exists");
        }

        Category parent = null;
        if (request.parentId() != null) {
            if (request.parentId().equals(id)) {
                throw new IllegalArgumentException("A category cannot be its own parent");
            }
            parent = categoryRepository.findById(request.parentId())
                    .orElseThrow(() -> new CategoryNotFoundException(request.parentId()));
        }

        category.setName(request.name());
        category.setDescription(request.description());
        category.setParent(parent);

        log.info("Category updated via CQRS: id={}, name={}", id, request.name());
        return categoryResponseMapper.toResponse(category);
    }
}
