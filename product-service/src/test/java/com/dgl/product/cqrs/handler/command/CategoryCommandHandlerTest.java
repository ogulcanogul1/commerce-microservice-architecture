package com.dgl.product.cqrs.handler.command;

import com.dgl.product.cqrs.command.CreateCategoryCommand;
import com.dgl.product.cqrs.command.DeleteCategoryCommand;
import com.dgl.product.cqrs.command.UpdateCategoryCommand;
import com.dgl.product.cqrs.mapper.CategoryResponseMapper;
import com.dgl.product.domain.Category;
import com.dgl.product.dto.request.CreateCategoryRequest;
import com.dgl.product.dto.request.UpdateCategoryRequest;
import com.dgl.product.dto.response.CategoryResponse;
import com.dgl.product.exception.CategoryAlreadyExistsException;
import com.dgl.product.exception.CategoryNotFoundException;
import com.dgl.product.repository.CategoryRepository;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import java.util.Optional;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.*;

@ExtendWith(MockitoExtension.class)
class CategoryCommandHandlerTest {

    @Mock
    private CategoryRepository categoryRepository;

    private final CategoryResponseMapper mapper = new CategoryResponseMapper();

    private CreateCategoryCommandHandler createHandler;
    private UpdateCategoryCommandHandler updateHandler;
    private DeleteCategoryCommandHandler deleteHandler;

    private UUID categoryId;
    private Category sampleCategory;

    @BeforeEach
    void setUp() {
        createHandler = new CreateCategoryCommandHandler(categoryRepository, mapper);
        updateHandler = new UpdateCategoryCommandHandler(categoryRepository, mapper);
        deleteHandler = new DeleteCategoryCommandHandler(categoryRepository);

        categoryId = UUID.randomUUID();
        sampleCategory = Category.builder()
                .id(categoryId)
                .name("Books")
                .slug("books")
                .description("All books")
                .build();
    }

    @Test
    @DisplayName("CreateCategory: Should persist category and return response")
    void createCategory_shouldSucceed() {
        CreateCategoryRequest request = new CreateCategoryRequest("Books", "All books", null);

        when(categoryRepository.existsByName("Books")).thenReturn(false);
        when(categoryRepository.existsBySlug("books")).thenReturn(false);
        when(categoryRepository.save(any(Category.class))).thenReturn(sampleCategory);

        CategoryResponse response = createHandler.handle(new CreateCategoryCommand(request));

        assertThat(response).isNotNull();
        assertThat(response.name()).isEqualTo("Books");
        verify(categoryRepository).save(any(Category.class));
    }

    @Test
    @DisplayName("CreateCategory: Duplicate name should throw CategoryAlreadyExistsException")
    void createCategory_duplicateName_shouldThrowException() {
        CreateCategoryRequest request = new CreateCategoryRequest("Books", "All books", null);
        when(categoryRepository.existsByName("Books")).thenReturn(true);

        assertThatThrownBy(() -> createHandler.handle(new CreateCategoryCommand(request)))
                .isInstanceOf(CategoryAlreadyExistsException.class);
    }

    @Test
    @DisplayName("UpdateCategory: Should update category name and description")
    void updateCategory_shouldSucceed() {
        UpdateCategoryRequest request = new UpdateCategoryRequest("Novels", "All novels", null);

        when(categoryRepository.findById(categoryId)).thenReturn(Optional.of(sampleCategory));
        when(categoryRepository.existsByName("Novels")).thenReturn(false);

        CategoryResponse response = updateHandler.handle(new UpdateCategoryCommand(categoryId, request));

        assertThat(response).isNotNull();
        assertThat(sampleCategory.getName()).isEqualTo("Novels");
    }

    @Test
    @DisplayName("DeleteCategory: Should delete existing category")
    void deleteCategory_shouldSucceed() {
        when(categoryRepository.existsById(categoryId)).thenReturn(true);

        deleteHandler.handle(new DeleteCategoryCommand(categoryId));

        verify(categoryRepository).deleteById(categoryId);
    }
}
