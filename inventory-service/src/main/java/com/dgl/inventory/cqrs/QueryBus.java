package com.dgl.inventory.cqrs;

/**
 * Dispatches queries to their registered {@link QueryHandler}.
 */
public interface QueryBus {

    /**
     * Executes the given query by dispatching it to its matching handler.
     *
     * @param <R> the expected result type
     * @param <Q> the query type
     * @param query the query to execute
     * @return the query result
     */
    <R, Q extends Query<R>> R execute(Q query);
}
