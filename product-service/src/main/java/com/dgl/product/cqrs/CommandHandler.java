package com.dgl.product.cqrs;

/**
 * Handler interface responsible for executing a specific {@link Command}.
 *
 * @param <C> the command type
 * @param <R> the return type of the command
 */
public interface CommandHandler<C extends Command<R>, R> {

    /**
     * Executes the business logic associated with the given command.
     *
     * @param command the command to handle
     * @return the result of executing the command
     */
    R handle(C command);
}
