package com.dgl.order.cqrs;

/**
 * Marker interface for a CQRS command that produces a result of type R.
 * For commands with no return value, use {@link Void}.
 *
 * @param <R> the return type of the command execution
 */
public interface Command<R> {
}
