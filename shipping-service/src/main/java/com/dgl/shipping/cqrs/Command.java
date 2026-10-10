package com.dgl.shipping.cqrs;

/**
 * Marker interface for all Shipping commands that produce a result of type {@link R}.
 *
 * @param <R> the return type of the command execution (use {@link Void} if no result)
 */
public interface Command<R> {
}
