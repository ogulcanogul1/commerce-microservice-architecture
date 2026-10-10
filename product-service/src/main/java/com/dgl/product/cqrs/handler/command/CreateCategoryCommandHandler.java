package com.dgl.product.cqrs.handler.command;

import com.dgl.product.config.RedisConfig;
import com.dgl.product.cqrs.CommandHandler;
import com.dgl.product.cqrs.command.CreateCategoryCommand;
import com.dgl.product.cqrs.mapper.CategoryResponseMapper;
import com.dgl.product.cqrs.util.SlugUtils;
import com.dgl.product.domain.Category;
import com.dgl.product.dto.request.CreateCategoryRequest;
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
public class CreateCategoryCommandHandler implements CommandHandler<CreateCategoryCommand, CategoryResponse> {

    private final CategoryRepository categoryRepository;
    private final CategoryResponseMapper categoryResponseMapper;

    @Override
    @Transactional
    @CacheEvict(value = RedisConfig.CATEGORIES_CACHE, allEntries = true)
    public CategoryResponse handle(CreateCategoryCommand command) {
        CreateCategoryRequest request = command.request();

        if (categoryRepository.existsByName(request.name())) {
            throw new CategoryAlreadyExistsException("Category with name '" + request.name() + "' already exists");
        }

        String slug = SlugUtils.toSlug(request.name());
        if (categoryRepository.existsBySlug(slug)) {
            slug = slug + "-" + UUID.randomUUID().toString().substring(0, 8);
        }

        Category parent = null;
        if (request.parentId() != null) {
            parent = categoryRepository.findById(request.parentId())
                    .orElseThrow(() -> new CategoryNotFoundException(request.parentId()));
        }

        Category category = Category.builder()
                .name(request.name())
                .slug(slug)
                .description(request.description())
                .parent(parent)
                .build();

        Category saved = categoryRepository.save(category);
        log.info("Category created via CQRS: id={}, slug={}", saved.getId(), saved.getSlug());
        return categoryResponseMapper.toResponse(saved);
    }
}
