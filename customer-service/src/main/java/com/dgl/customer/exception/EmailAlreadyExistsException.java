package com.dgl.customer.exception;

public class EmailAlreadyExistsException extends BusinessRuleException {

    public EmailAlreadyExistsException(String message) {
        super(message);
    }
}
