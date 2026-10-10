package com.dgl.product.cqrs.handler.query;

import com.dgl.product.config.RedisConfig;
import com.dgl.product.cqrs.QueryHandler;
import com.dgl.product.cqrs.mapper.ProductResponseMapper;
import com.dgl.product.cqrs.query.GetProductByIdQuery;
import com.dgl.product.domain.Product;
import com.dgl.product.dto.response.ProductResponse;
import com.dgl.product.exception.ProductNotFoundException;
import com.dgl.product.repository.ProductRepository;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;

@Slf4j
@Component
@RequiredArgsConstructor
public class GetProductByIdQueryHandler implements QueryHandler<GetProductByIdQuery, ProductResponse> {

    private final ProductRepository productRepository;
    private final ProductResponseMapper productResponseMapper;

    @Override
    @Transactional(readOnly = true)
    @Cacheable(value = RedisConfig.PRODUCTS_CACHE, key = "#query.id()")
    public ProductResponse handle(GetProductByIdQuery query) {
        log.debug("Executing GetProductByIdQuery for id: {}", query.id());
        Product product = productRepository.findById(query.id())
                .orElseThrow(() -> new ProductNotFoundException(query.id()));
        return productResponseMapper.toResponse(product);
    }
}
