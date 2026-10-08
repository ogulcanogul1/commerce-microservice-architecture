package com.dgl.product.service;

import com.dgl.product.domain.Category;
import com.dgl.product.dto.request.CreateCategoryRequest;
import com.dgl.product.dto.request.UpdateCategoryRequest;
import com.dgl.product.dto.response.CategoryResponse;
import com.dgl.product.exception.CategoryAlreadyExistsException;
import com.dgl.product.exception.CategoryNotFoundException;
import com.dgl.product.repository.CategoryRepository;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import java.time.Instant;
import java.util.List;
import java.util.Optional;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.*;

@ExtendWith(MockitoExtension.class)
class CategoryServiceImplTest {

    @Mock
    private CategoryRepository categoryRepository;

    @InjectMocks
    private CategoryServiceImpl categoryService;

    @Test
    @DisplayName("createCategory should succeed and generate slug when valid request provided")
    void createCategory_WhenValid_ShouldSucceed() {
        CreateCategoryRequest request = new CreateCategoryRequest("Smart Phones", "All smart phones", null);

        when(categoryRepository.existsByName("Smart Phones")).thenReturn(false);
        when(categoryRepository.existsBySlug("smart-phones")).thenReturn(false);

        when(categoryRepository.save(any(Category.class))).thenAnswer(invocation -> {
            Category c = invocation.getArgument(0);
            c.setId(UUID.randomUUID());
            c.setCreatedAt(Instant.now());
            c.setUpdatedAt(Instant.now());
            return c;
        });

        CategoryResponse response = categoryService.createCategory(request);

        assertThat(response).isNotNull();
        assertThat(response.name()).isEqualTo("Smart Phones");
        assertThat(response.slug()).isEqualTo("smart-phones");
        verify(categoryRepository, times(1)).save(any(Category.class));
    }

    @Test
    @DisplayName("createCategory should throw CategoryAlreadyExistsException when name exists")
    void createCategory_WhenNameExists_ShouldThrowException() {
        CreateCategoryRequest request = new CreateCategoryRequest("Existing Category", "Description", null);

        when(categoryRepository.existsByName("Existing Category")).thenReturn(true);

        assertThatThrownBy(() -> categoryService.createCategory(request))
                .isInstanceOf(CategoryAlreadyExistsException.class)
                .hasMessageContaining("Existing Category");

        verify(categoryRepository, never()).save(any(Category.class));
    }

    @Test
    @DisplayName("createCategory should throw CategoryNotFoundException when parent does not exist")
    void createCategory_WhenParentNotFound_ShouldThrowException() {
        UUID parentId = UUID.randomUUID();
        CreateCategoryRequest request = new CreateCategoryRequest("Child Category", "Description", parentId);

        when(categoryRepository.existsByName("Child Category")).thenReturn(false);
        when(categoryRepository.existsBySlug("child-category")).thenReturn(false);
        when(categoryRepository.findById(parentId)).thenReturn(Optional.empty());

        assertThatThrownBy(() -> categoryService.createCategory(request))
                .isInstanceOf(CategoryNotFoundException.class);
    }

    @Test
    @DisplayName("updateCategory should update category successfully")
    void updateCategory_WhenValid_ShouldSucceed() {
        UUID categoryId = UUID.randomUUID();
        Category category = Category.builder()
                .id(categoryId)
                .name("Old Category")
                .slug("old-category")
                .description("Old Desc")
                .build();

        UpdateCategoryRequest request = new UpdateCategoryRequest("Updated Category", "Updated Desc", null);

        when(categoryRepository.findById(categoryId)).thenReturn(Optional.of(category));
        when(categoryRepository.existsByName("Updated Category")).thenReturn(false);

        CategoryResponse response = categoryService.updateCategory(categoryId, request);

        assertThat(response).isNotNull();
        assertThat(category.getName()).isEqualTo("Updated Category");
        assertThat(category.getDescription()).isEqualTo("Updated Desc");
    }

    @Test
    @DisplayName("updateCategory should throw IllegalArgumentException when category is set as its own parent")
    void updateCategory_WhenSelfParenting_ShouldThrowException() {
        UUID categoryId = UUID.randomUUID();
        Category category = Category.builder()
                .id(categoryId)
                .name("Self Category")
                .build();

        UpdateCategoryRequest request = new UpdateCategoryRequest("Self Category", "Desc", categoryId);

        when(categoryRepository.findById(categoryId)).thenReturn(Optional.of(category));

        assertThatThrownBy(() -> categoryService.updateCategory(categoryId, request))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessageContaining("cannot be its own parent");
    }

    @Test
    @DisplayName("getCategoryById should return response when category exists")
    void getCategoryById_WhenExists_ShouldReturnResponse() {
        UUID categoryId = UUID.randomUUID();
        Category category = Category.builder()
                .id(categoryId)
                .name("Gadgets")
                .slug("gadgets")
                .build();

        when(categoryRepository.findById(categoryId)).thenReturn(Optional.of(category));

        CategoryResponse response = categoryService.getCategoryById(categoryId);

        assertThat(response).isNotNull();
        assertThat(response.id()).isEqualTo(categoryId);
        assertThat(response.name()).isEqualTo("Gadgets");
    }

    @Test
    @DisplayName("getCategoryById should throw CategoryNotFoundException when category does not exist")
    void getCategoryById_WhenNotFound_ShouldThrowException() {
        UUID categoryId = UUID.randomUUID();
        when(categoryRepository.findById(categoryId)).thenReturn(Optional.empty());

        assertThatThrownBy(() -> categoryService.getCategoryById(categoryId))
                .isInstanceOf(CategoryNotFoundException.class);
    }

    @Test
    @DisplayName("deleteCategory should delete category when exists")
    void deleteCategory_WhenExists_ShouldDelete() {
        UUID categoryId = UUID.randomUUID();
        when(categoryRepository.existsById(categoryId)).thenReturn(true);

        categoryService.deleteCategory(categoryId);

        verify(categoryRepository, times(1)).deleteById(categoryId);
    }

    @Test
    @DisplayName("deleteCategory should throw CategoryNotFoundException when category does not exist")
    void deleteCategory_WhenNotFound_ShouldThrowException() {
        UUID categoryId = UUID.randomUUID();
        when(categoryRepository.existsById(categoryId)).thenReturn(false);

        assertThatThrownBy(() -> categoryService.deleteCategory(categoryId))
                .isInstanceOf(CategoryNotFoundException.class);

        verify(categoryRepository, never()).deleteById(any(UUID.class));
    }
}
