package com.dgl.product.cqrs.handler.query;

import com.dgl.product.config.RedisConfig;
import com.dgl.product.cqrs.QueryHandler;
import com.dgl.product.cqrs.mapper.CategoryResponseMapper;
import com.dgl.product.cqrs.query.GetAllCategoriesQuery;
import com.dgl.product.dto.response.CategoryResponse;
import com.dgl.product.repository.CategoryRepository;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;

import java.util.List;

@Slf4j
@Component
@RequiredArgsConstructor
public class GetAllCategoriesQueryHandler implements QueryHandler<GetAllCategoriesQuery, List<CategoryResponse>> {

    private final CategoryRepository categoryRepository;
    private final CategoryResponseMapper categoryResponseMapper;

    @Override
    @Transactional(readOnly = true)
    @Cacheable(value = RedisConfig.CATEGORIES_CACHE, key = "'all'")
    public List<CategoryResponse> handle(GetAllCategoriesQuery query) {
        log.debug("Executing GetAllCategoriesQuery");
        return categoryRepository.findAll().stream()
                .map(categoryResponseMapper::toResponse)
                .toList();
    }
}
