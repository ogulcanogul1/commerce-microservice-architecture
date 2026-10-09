package com.dgl.customer.exception;

public class InvalidCredentialsException extends BusinessRuleException {

    public InvalidCredentialsException(String message) {
        super(message);
    }

    public InvalidCredentialsException() {
        super("Invalid email or password");
    }
}
