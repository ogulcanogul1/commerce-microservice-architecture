package com.dgl.customer.exception;

public class InvalidTokenException extends BusinessRuleException {

    public InvalidTokenException(String message) {
        super(message);
    }

    public InvalidTokenException() {
        super("Invalid or expired token");
    }
}
