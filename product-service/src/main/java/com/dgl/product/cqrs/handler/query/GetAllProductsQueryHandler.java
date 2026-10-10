package com.dgl.product.cqrs.handler.query;

import com.dgl.product.cqrs.QueryHandler;
import com.dgl.product.cqrs.mapper.ProductResponseMapper;
import com.dgl.product.cqrs.query.GetAllProductsQuery;
import com.dgl.product.dto.response.ProductResponse;
import com.dgl.product.repository.ProductRepository;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.data.domain.Page;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;

@Slf4j
@Component
@RequiredArgsConstructor
public class GetAllProductsQueryHandler implements QueryHandler<GetAllProductsQuery, Page<ProductResponse>> {

    private final ProductRepository productRepository;
    private final ProductResponseMapper productResponseMapper;

    @Override
    @Transactional(readOnly = true)
    public Page<ProductResponse> handle(GetAllProductsQuery query) {
        log.debug("Executing GetAllProductsQuery");
        return productRepository.findAll(query.pageable())
                .map(productResponseMapper::toResponse);
    }
}
