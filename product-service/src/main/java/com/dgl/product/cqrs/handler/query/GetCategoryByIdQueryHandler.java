package com.dgl.product.cqrs.handler.query;

import com.dgl.product.config.RedisConfig;
import com.dgl.product.cqrs.QueryHandler;
import com.dgl.product.cqrs.mapper.CategoryResponseMapper;
import com.dgl.product.cqrs.query.GetCategoryByIdQuery;
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
public class GetCategoryByIdQueryHandler implements QueryHandler<GetCategoryByIdQuery, CategoryResponse> {

    private final CategoryRepository categoryRepository;
    private final CategoryResponseMapper categoryResponseMapper;

    @Override
    @Transactional(readOnly = true)
    @Cacheable(value = RedisConfig.CATEGORIES_CACHE, key = "#query.id()")
    public CategoryResponse handle(GetCategoryByIdQuery query) {
        log.debug("Executing GetCategoryByIdQuery for id: {}", query.id());
        Category category = categoryRepository.findById(query.id())
                .orElseThrow(() -> new CategoryNotFoundException(query.id()));
        return categoryResponseMapper.toResponse(category);
    }
}
