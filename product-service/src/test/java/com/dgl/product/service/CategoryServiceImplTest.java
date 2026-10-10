package com.dgl.product.service;

import com.dgl.product.cqrs.CommandBus;
import com.dgl.product.cqrs.QueryBus;
import com.dgl.product.cqrs.command.CreateCategoryCommand;
import com.dgl.product.cqrs.command.DeleteCategoryCommand;
import com.dgl.product.cqrs.command.UpdateCategoryCommand;
import com.dgl.product.cqrs.query.GetAllCategoriesQuery;
import com.dgl.product.cqrs.query.GetCategoryByIdQuery;
import com.dgl.product.cqrs.query.GetCategoryBySlugQuery;
import com.dgl.product.dto.request.CreateCategoryRequest;
import com.dgl.product.dto.request.UpdateCategoryRequest;
import com.dgl.product.dto.response.CategoryResponse;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import java.util.List;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.*;

@ExtendWith(MockitoExtension.class)
class CategoryServiceImplTest {

    @Mock
    private CommandBus commandBus;

    @Mock
    private QueryBus queryBus;

    @InjectMocks
    private CategoryServiceImpl categoryService;

    @Test
    @DisplayName("createCategory: Should dispatch CreateCategoryCommand")
    void createCategory_shouldDispatch() {
        CreateCategoryRequest request = new CreateCategoryRequest("Electronics", "Desc", null);
        CategoryResponse expected = mock(CategoryResponse.class);

        when(commandBus.execute(any(CreateCategoryCommand.class))).thenReturn(expected);

        CategoryResponse actual = categoryService.createCategory(request);

        assertThat(actual).isSameAs(expected);
        verify(commandBus).execute(new CreateCategoryCommand(request));
    }

    @Test
    @DisplayName("updateCategory: Should dispatch UpdateCategoryCommand")
    void updateCategory_shouldDispatch() {
        UUID id = UUID.randomUUID();
        UpdateCategoryRequest request = new UpdateCategoryRequest("Books", "Desc", null);
        CategoryResponse expected = mock(CategoryResponse.class);

        when(commandBus.execute(any(UpdateCategoryCommand.class))).thenReturn(expected);

        CategoryResponse actual = categoryService.updateCategory(id, request);

        assertThat(actual).isSameAs(expected);
        verify(commandBus).execute(new UpdateCategoryCommand(id, request));
    }

    @Test
    @DisplayName("getCategoryById: Should dispatch GetCategoryByIdQuery")
    void getCategoryById_shouldDispatch() {
        UUID id = UUID.randomUUID();
        CategoryResponse expected = mock(CategoryResponse.class);

        when(queryBus.execute(any(GetCategoryByIdQuery.class))).thenReturn(expected);

        CategoryResponse actual = categoryService.getCategoryById(id);

        assertThat(actual).isSameAs(expected);
        verify(queryBus).execute(new GetCategoryByIdQuery(id));
    }

    @Test
    @DisplayName("getCategoryBySlug: Should dispatch GetCategoryBySlugQuery")
    void getCategoryBySlug_shouldDispatch() {
        CategoryResponse expected = mock(CategoryResponse.class);

        when(queryBus.execute(any(GetCategoryBySlugQuery.class))).thenReturn(expected);

        CategoryResponse actual = categoryService.getCategoryBySlug("electronics");

        assertThat(actual).isSameAs(expected);
        verify(queryBus).execute(new GetCategoryBySlugQuery("electronics"));
    }

    @Test
    @DisplayName("getAllCategories: Should dispatch GetAllCategoriesQuery")
    void getAllCategories_shouldDispatch() {
        when(queryBus.execute(any(GetAllCategoriesQuery.class))).thenReturn(List.of());

        List<CategoryResponse> actual = categoryService.getAllCategories();

        assertThat(actual).isEmpty();
        verify(queryBus).execute(new GetAllCategoriesQuery());
    }

    @Test
    @DisplayName("deleteCategory: Should dispatch DeleteCategoryCommand")
    void deleteCategory_shouldDispatch() {
        UUID id = UUID.randomUUID();

        categoryService.deleteCategory(id);

        verify(commandBus).execute(new DeleteCategoryCommand(id));
    }
}
