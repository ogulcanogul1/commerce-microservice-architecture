package com.dgl.product.cqrs;

/**
 * Dispatches commands to their registered {@link CommandHandler}.
 */
public interface CommandBus {

    /**
     * Executes the given command by dispatching it to its matching handler.
     *
     * @param <R> the expected result type
     * @param <C> the command type
     * @param command the command to execute
     * @return the handler result
     */
    <R, C extends Command<R>> R execute(C command);
}
