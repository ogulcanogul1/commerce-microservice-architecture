package com.dgl.customer.exception;

public class AccessDeniedException extends BusinessRuleException {

    public AccessDeniedException(String message) {
        super(message);
    }
}
