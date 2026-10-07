package com.dgl.customer.outbox;

public enum OutboxStatus {
    PENDING,
    PUBLISHED,
    FAILED
}
