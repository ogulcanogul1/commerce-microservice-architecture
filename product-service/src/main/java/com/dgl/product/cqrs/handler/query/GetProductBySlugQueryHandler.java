package com.dgl.product.cqrs.handler.query;

import com.dgl.product.config.RedisConfig;
import com.dgl.product.cqrs.QueryHandler;
import com.dgl.product.cqrs.mapper.ProductResponseMapper;
import com.dgl.product.cqrs.query.GetProductBySlugQuery;
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
public class GetProductBySlugQueryHandler implements QueryHandler<GetProductBySlugQuery, ProductResponse> {

    private final ProductRepository productRepository;
    private final ProductResponseMapper productResponseMapper;

    @Override
    @Transactional(readOnly = true)
    @Cacheable(value = RedisConfig.PRODUCT_SLUGS_CACHE, key = "#query.slug()")
    public ProductResponse handle(GetProductBySlugQuery query) {
        log.debug("Executing GetProductBySlugQuery for slug: {}", query.slug());
        Product product = productRepository.findBySlug(query.slug())
                .orElseThrow(() -> new ProductNotFoundException("Product not found with slug: " + query.slug()));
        return productResponseMapper.toResponse(product);
    }
}
