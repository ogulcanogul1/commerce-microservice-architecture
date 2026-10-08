package com.dgl.order.exception;

/**
 * Marker interface for transient errors that can be retried (e.g. network timeout, 503, deadlock).
 */
public interface Retryable {
}
