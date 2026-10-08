package com.dgl.customer.exception;

public abstract class TransientException extends RuntimeException implements Retryable {

    protected TransientException(String message) {
        super(message);
    }

    protected TransientException(String message, Throwable cause) {
        super(message, cause);
    }
}
