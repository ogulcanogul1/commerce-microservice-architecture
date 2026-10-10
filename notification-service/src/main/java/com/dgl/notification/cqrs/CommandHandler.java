package com.dgl.notification.cqrs;

/**
 * Handles a specific {@link Command} type and returns a result of type {@link R}.
 *
 * @param <C> the command type
 * @param <R> the return type
 */
@FunctionalInterface
public interface CommandHandler<C extends Command<R>, R> {

    /**
     * Executes business logic associated with the given command.
     *
     * @param command the command to handle
     * @return the execution result
     */
    R handle(C command);
}
