package com.dgl.payment.outbox;

public enum OutboxStatus {
    PENDING,
    PUBLISHED,
    FAILED
}
