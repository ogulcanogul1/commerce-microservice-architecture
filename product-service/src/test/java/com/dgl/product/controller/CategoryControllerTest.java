package com.dgl.product.controller;

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
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;

import java.util.List;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.*;

@ExtendWith(MockitoExtension.class)
class CategoryControllerTest {

    @Mock
    private CommandBus commandBus;

    @Mock
    private QueryBus queryBus;

    @InjectMocks
    private CategoryController controller;

    private UUID categoryId;
    private CategoryResponse mockResponse;

    @BeforeEach
    void setUp() {
        categoryId = UUID.randomUUID();
        mockResponse = mock(CategoryResponse.class);
    }

    @Test
    @DisplayName("CreateCategory: Should dispatch command and return 201")
    void createCategory_shouldReturn201() {
        CreateCategoryRequest request = new CreateCategoryRequest("Electronics", "Desc", null);
        when(commandBus.execute(any(CreateCategoryCommand.class))).thenReturn(mockResponse);

        ResponseEntity<CategoryResponse> response = controller.createCategory(request);

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.CREATED);
        assertThat(response.getBody()).isSameAs(mockResponse);
        verify(commandBus).execute(new CreateCategoryCommand(request));
    }

    @Test
    @DisplayName("GetCategoryById: Should dispatch query and return 200")
    void getCategoryById_shouldReturn200() {
        when(queryBus.execute(any(GetCategoryByIdQuery.class))).thenReturn(mockResponse);

        ResponseEntity<CategoryResponse> response = controller.getCategoryById(categoryId);

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.OK);
        verify(queryBus).execute(new GetCategoryByIdQuery(categoryId));
    }

    @Test
    @DisplayName("GetCategoryBySlug: Should dispatch query and return 200")
    void getCategoryBySlug_shouldReturn200() {
        when(queryBus.execute(any(GetCategoryBySlugQuery.class))).thenReturn(mockResponse);

        ResponseEntity<CategoryResponse> response = controller.getCategoryBySlug("electronics");

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.OK);
        verify(queryBus).execute(new GetCategoryBySlugQuery("electronics"));
    }

    @Test
    @DisplayName("GetAllCategories: Should dispatch query and return 200")
    void getAllCategories_shouldReturn200() {
        when(queryBus.execute(any(GetAllCategoriesQuery.class))).thenReturn(List.of(mockResponse));

        ResponseEntity<List<CategoryResponse>> response = controller.getAllCategories();

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.OK);
        verify(queryBus).execute(new GetAllCategoriesQuery());
    }

    @Test
    @DisplayName("UpdateCategory: Should dispatch command and return 200")
    void updateCategory_shouldReturn200() {
        UpdateCategoryRequest request = new UpdateCategoryRequest("Books", "Desc", null);
        when(commandBus.execute(any(UpdateCategoryCommand.class))).thenReturn(mockResponse);

        ResponseEntity<CategoryResponse> response = controller.updateCategory(categoryId, request);

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.OK);
        verify(commandBus).execute(new UpdateCategoryCommand(categoryId, request));
    }

    @Test
    @DisplayName("DeleteCategory: Should dispatch command")
    void deleteCategory_shouldDispatch() {
        controller.deleteCategory(categoryId);
        verify(commandBus).execute(new DeleteCategoryCommand(categoryId));
    }
}
