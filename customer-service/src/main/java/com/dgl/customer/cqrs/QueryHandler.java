package com.dgl.customer.cqrs;

/**
 * Handles a specific {@link Query} type and returns data of type {@link R}.
 *
 * @param <Q> the query type
 * @param <R> the return type
 */
@FunctionalInterface
public interface QueryHandler<Q extends Query<R>, R> {

    /**
     * Executes read-only logic associated with the given query.
     *
     * @param query the query to handle
     * @return the query result
     */
    R handle(Q query);
}
