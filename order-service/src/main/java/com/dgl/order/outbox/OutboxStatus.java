package com.dgl.order.outbox;

public enum OutboxStatus {
    PENDING,
    PUBLISHED,
    FAILED
}
