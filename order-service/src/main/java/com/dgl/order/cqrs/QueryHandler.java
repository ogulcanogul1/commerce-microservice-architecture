package com.dgl.order.cqrs;

/**
 * Handler interface responsible for executing a specific {@link Query}.
 *
 * @param <Q> the query type
 * @param <R> the return type of the query
 */
public interface QueryHandler<Q extends Query<R>, R> {

    /**
     * Executes the query logic and returns the retrieved data.
     *
     * @param query the query to handle
     * @return the result of executing the query
     */
    R handle(Q query);
}
