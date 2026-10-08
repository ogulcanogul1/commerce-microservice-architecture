package com.dgl.product.exception;

public class ProductAlreadyExistsException extends BusinessRuleException {

    public ProductAlreadyExistsException(String message) {
        super(message);
    }
}
