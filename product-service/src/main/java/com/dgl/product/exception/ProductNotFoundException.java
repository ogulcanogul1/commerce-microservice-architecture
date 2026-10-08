package com.dgl.product.exception;

import java.util.UUID;

public class ProductNotFoundException extends BusinessRuleException {

    public ProductNotFoundException(UUID id) {
        super("Product not found with ID: " + id);
    }

    public ProductNotFoundException(String message) {
        super(message);
    }
}
