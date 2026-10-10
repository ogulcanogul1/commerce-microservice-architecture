package com.dgl.product.cqrs.handler.query;

import com.dgl.product.cqrs.QueryHandler;
import com.dgl.product.cqrs.mapper.ProductResponseMapper;
import com.dgl.product.cqrs.query.GetProductsByCategoryQuery;
import com.dgl.product.dto.response.ProductResponse;
import com.dgl.product.exception.CategoryNotFoundException;
import com.dgl.product.repository.CategoryRepository;
import com.dgl.product.repository.ProductRepository;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.data.domain.Page;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;

@Slf4j
@Component
@RequiredArgsConstructor
public class GetProductsByCategoryQueryHandler implements QueryHandler<GetProductsByCategoryQuery, Page<ProductResponse>> {

    private final ProductRepository productRepository;
    private final CategoryRepository categoryRepository;
    private final ProductResponseMapper productResponseMapper;

    @Override
    @Transactional(readOnly = true)
    public Page<ProductResponse> handle(GetProductsByCategoryQuery query) {
        log.debug("Executing GetProductsByCategoryQuery for categoryId: {}", query.categoryId());
        if (!categoryRepository.existsById(query.categoryId())) {
            throw new CategoryNotFoundException(query.categoryId());
        }
        return productRepository.findByCategoryId(query.categoryId(), query.pageable())
                .map(productResponseMapper::toResponse);
    }
}
