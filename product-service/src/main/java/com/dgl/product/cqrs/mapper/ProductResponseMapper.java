package com.dgl.product.cqrs.mapper;

import com.dgl.product.domain.Product;
import com.dgl.product.domain.ProductAttribute;
import com.dgl.product.dto.response.ProductResponse;
import org.springframework.stereotype.Component;

import java.util.Collections;
import java.util.Map;
import java.util.stream.Collectors;

@Component
public class ProductResponseMapper {

    public ProductResponse toResponse(Product product) {
        if (product == null) {
            return null;
        }

        Map<String, String> attributesMap = product.getAttributes() != null
                ? product.getAttributes().stream()
                .collect(Collectors.toMap(
                        ProductAttribute::getAttributeKey,
                        ProductAttribute::getAttributeValue,
                        (existing, replacement) -> replacement))
                : Collections.emptyMap();

        return new ProductResponse(
                product.getId(),
                product.getSku(),
                product.getName(),
                product.getSlug(),
                product.getDescription(),
                product.getCategory() != null ? product.getCategory().getId() : null,
                product.getCategory() != null ? product.getCategory().getName() : null,
                product.getBasePrice(),
                product.getCurrency(),
                product.getStatus(),
                attributesMap,
                product.getCreatedAt(),
                product.getUpdatedAt()
        );
    }
}
