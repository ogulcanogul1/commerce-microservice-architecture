package com.dgl.payment.cqrs.bus;

import com.dgl.payment.cqrs.Command;
import com.dgl.payment.cqrs.CommandBus;
import com.dgl.payment.cqrs.CommandHandler;
import lombok.extern.slf4j.Slf4j;
import org.springframework.core.ResolvableType;
import org.springframework.stereotype.Component;
import org.springframework.util.ClassUtils;

import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

/**
 * Lightweight Spring implementation of {@link CommandBus} for payment-service.
 */
@Slf4j
@Component
public class SimpleCommandBus implements CommandBus {

    private final Map<Class<? extends Command<?>>, CommandHandler<?, ?>> handlers = new ConcurrentHashMap<>();

    public SimpleCommandBus(List<CommandHandler<?, ?>> handlerList) {
        for (CommandHandler<?, ?> handler : handlerList) {
            Class<?> userClass = ClassUtils.getUserClass(handler);
            Class<?> commandType = ResolvableType.forClass(userClass)
                    .as(CommandHandler.class)
                    .getGeneric(0)
                    .resolve();

            if (commandType != null && Command.class.isAssignableFrom(commandType)) {
                @SuppressWarnings("unchecked")
                Class<? extends Command<?>> typedCommand = (Class<? extends Command<?>>) commandType;
                handlers.put(typedCommand, handler);
                log.info("Registered CommandHandler [{}] for command [{}]", userClass.getSimpleName(), typedCommand.getSimpleName());
            } else {
                log.warn("Could not resolve Command type for handler [{}]", userClass.getName());
            }
        }
    }

    @Override
    @SuppressWarnings("unchecked")
    public <R, C extends Command<R>> R execute(C command) {
        if (command == null) {
            throw new IllegalArgumentException("Command cannot be null");
        }

        CommandHandler<C, R> handler = (CommandHandler<C, R>) handlers.get(command.getClass());
        if (handler == null) {
            throw new IllegalStateException("No CommandHandler registered for command: " + command.getClass().getName());
        }

        log.debug("Dispatching command [{}] to handler [{}]", command.getClass().getSimpleName(), handler.getClass().getSimpleName());
        return handler.handle(command);
    }
}
