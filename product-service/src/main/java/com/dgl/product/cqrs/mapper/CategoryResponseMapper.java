package com.dgl.product.cqrs.mapper;

import com.dgl.product.domain.Category;
import com.dgl.product.dto.response.CategoryResponse;
import org.springframework.stereotype.Component;

import java.util.Collections;
import java.util.List;

@Component
public class CategoryResponseMapper {

    public CategoryResponse toResponse(Category category) {
        if (category == null) {
            return null;
        }

        List<CategoryResponse> subs = category.getSubCategories() != null
                ? category.getSubCategories().stream().map(this::toResponse).toList()
                : Collections.emptyList();

        return new CategoryResponse(
                category.getId(),
                category.getName(),
                category.getSlug(),
                category.getDescription(),
                category.getParent() != null ? category.getParent().getId() : null,
                subs,
                category.getCreatedAt(),
                category.getUpdatedAt()
        );
    }
}
