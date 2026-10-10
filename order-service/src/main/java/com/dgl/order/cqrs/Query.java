package com.dgl.order.cqrs;

/**
 * Marker interface for a CQRS query that retrieves data of type R without side effects.
 *
 * @param <R> the return type of the query execution
 */
public interface Query<R> {
}
