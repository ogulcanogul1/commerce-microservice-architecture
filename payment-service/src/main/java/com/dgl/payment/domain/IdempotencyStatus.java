package com.dgl.payment.domain;

public enum IdempotencyStatus {
    PROCESSING,
    COMPLETED,
    FAILED
}
