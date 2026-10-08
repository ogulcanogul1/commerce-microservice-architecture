package com.dgl.product.exception;

import java.util.UUID;

public class CategoryNotFoundException extends BusinessRuleException {

    public CategoryNotFoundException(UUID id) {
        super("Category not found with ID: " + id);
    }

    public CategoryNotFoundException(String message) {
        super(message);
    }
}
