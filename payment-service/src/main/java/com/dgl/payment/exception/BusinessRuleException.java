package com.dgl.payment.exception;

public abstract class BusinessRuleException extends RuntimeException implements NonRetryable {

    protected BusinessRuleException(String message) {
        super(message);
    }

    protected BusinessRuleException(String message, Throwable cause) {
        super(message, cause);
    }
}
