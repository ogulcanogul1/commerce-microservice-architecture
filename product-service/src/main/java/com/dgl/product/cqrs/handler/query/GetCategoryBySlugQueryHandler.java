package com.dgl.product.cqrs.handler.query;

import com.dgl.product.config.RedisConfig;
import com.dgl.product.cqrs.QueryHandler;
import com.dgl.product.cqrs.mapper.CategoryResponseMapper;
import com.dgl.product.cqrs.query.GetCategoryBySlugQuery;
import com.dgl.product.domain.Category;
import com.dgl.product.dto.response.CategoryResponse;
import com.dgl.product.exception.CategoryNotFoundException;
import com.dgl.product.repository.CategoryRepository;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;

@Slf4j
@Component
@RequiredArgsConstructor
public class GetCategoryBySlugQueryHandler implements QueryHandler<GetCategoryBySlugQuery, CategoryResponse> {

    private final CategoryRepository categoryRepository;
    private final CategoryResponseMapper categoryResponseMapper;

    @Override
    @Transactional(readOnly = true)
    @Cacheable(value = RedisConfig.CATEGORIES_CACHE, key = "#query.slug()")
    public CategoryResponse handle(GetCategoryBySlugQuery query) {
        log.debug("Executing GetCategoryBySlugQuery for slug: {}", query.slug());
        Category category = categoryRepository.findBySlug(query.slug())
                .orElseThrow(() -> new CategoryNotFoundException("Category not found with slug: " + query.slug()));
        return categoryResponseMapper.toResponse(category);
    }
}
