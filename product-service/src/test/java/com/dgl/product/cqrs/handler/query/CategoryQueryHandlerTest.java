package com.dgl.product.cqrs.handler.query;

import com.dgl.product.cqrs.mapper.CategoryResponseMapper;
import com.dgl.product.cqrs.query.GetAllCategoriesQuery;
import com.dgl.product.cqrs.query.GetCategoryByIdQuery;
import com.dgl.product.cqrs.query.GetCategoryBySlugQuery;
import com.dgl.product.domain.Category;
import com.dgl.product.dto.response.CategoryResponse;
import com.dgl.product.exception.CategoryNotFoundException;
import com.dgl.product.repository.CategoryRepository;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import java.util.List;
import java.util.Optional;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class CategoryQueryHandlerTest {

    @Mock
    private CategoryRepository categoryRepository;

    private final CategoryResponseMapper mapper = new CategoryResponseMapper();

    private GetCategoryByIdQueryHandler getByIdHandler;
    private GetCategoryBySlugQueryHandler getBySlugHandler;
    private GetAllCategoriesQueryHandler getAllHandler;

    private UUID categoryId;
    private Category sampleCategory;

    @BeforeEach
    void setUp() {
        getByIdHandler = new GetCategoryByIdQueryHandler(categoryRepository, mapper);
        getBySlugHandler = new GetCategoryBySlugQueryHandler(categoryRepository, mapper);
        getAllHandler = new GetAllCategoriesQueryHandler(categoryRepository, mapper);

        categoryId = UUID.randomUUID();
        sampleCategory = Category.builder()
                .id(categoryId)
                .name("Home & Living")
                .slug("home-living")
                .description("Home decor")
                .build();
    }

    @Test
    @DisplayName("GetCategoryById: Should return category response")
    void getCategoryById_shouldSucceed() {
        when(categoryRepository.findById(categoryId)).thenReturn(Optional.of(sampleCategory));

        CategoryResponse response = getByIdHandler.handle(new GetCategoryByIdQuery(categoryId));

        assertThat(response).isNotNull();
        assertThat(response.id()).isEqualTo(categoryId);
    }

    @Test
    @DisplayName("GetCategoryBySlug: Should return category response")
    void getCategoryBySlug_shouldSucceed() {
        when(categoryRepository.findBySlug("home-living")).thenReturn(Optional.of(sampleCategory));

        CategoryResponse response = getBySlugHandler.handle(new GetCategoryBySlugQuery("home-living"));

        assertThat(response).isNotNull();
        assertThat(response.slug()).isEqualTo("home-living");
    }

    @Test
    @DisplayName("GetAllCategories: Should return list of all categories")
    void getAllCategories_shouldSucceed() {
        when(categoryRepository.findAll()).thenReturn(List.of(sampleCategory));

        List<CategoryResponse> response = getAllHandler.handle(new GetAllCategoriesQuery());

        assertThat(response).hasSize(1);
    }
}
