package com.dgl.payment.exception;

public class IdempotencyConflictException extends BusinessRuleException {

    public IdempotencyConflictException(String message) {
        super(message);
    }
}
