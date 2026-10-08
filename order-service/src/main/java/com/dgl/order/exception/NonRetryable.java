package com.dgl.order.exception;

/**
 * Marker interface for permanent/business rule errors that should NOT be retried (e.g. 4xx, business logic violations).
 */
public interface NonRetryable {
}
