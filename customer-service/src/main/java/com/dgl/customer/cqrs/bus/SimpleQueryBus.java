package com.dgl.customer.cqrs.bus;

import com.dgl.customer.cqrs.Query;
import com.dgl.customer.cqrs.QueryBus;
import com.dgl.customer.cqrs.QueryHandler;
import lombok.extern.slf4j.Slf4j;
import org.springframework.core.ResolvableType;
import org.springframework.stereotype.Component;
import org.springframework.util.ClassUtils;

import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

/**
 * Lightweight Spring implementation of {@link QueryBus} for customer-service.
 */
@Slf4j
@Component
public class SimpleQueryBus implements QueryBus {

    private final Map<Class<? extends Query<?>>, QueryHandler<?, ?>> handlers = new ConcurrentHashMap<>();

    public SimpleQueryBus(List<QueryHandler<?, ?>> handlerList) {
        for (QueryHandler<?, ?> handler : handlerList) {
            Class<?> userClass = ClassUtils.getUserClass(handler);
            Class<?> queryType = ResolvableType.forClass(userClass)
                    .as(QueryHandler.class)
                    .getGeneric(0)
                    .resolve();

            if (queryType != null && Query.class.isAssignableFrom(queryType)) {
                @SuppressWarnings("unchecked")
                Class<? extends Query<?>> typedQuery = (Class<? extends Query<?>>) queryType;
                handlers.put(typedQuery, handler);
                log.info("Registered QueryHandler [{}] for query [{}]", userClass.getSimpleName(), typedQuery.getSimpleName());
            } else {
                log.warn("Could not resolve Query type for handler [{}]", userClass.getName());
            }
        }
    }

    @Override
    @SuppressWarnings("unchecked")
    public <R, Q extends Query<R>> R execute(Q query) {
        if (query == null) {
            throw new IllegalArgumentException("Query cannot be null");
        }

        QueryHandler<Q, R> handler = (QueryHandler<Q, R>) handlers.get(query.getClass());
        if (handler == null) {
            throw new IllegalStateException("No QueryHandler registered for query: " + query.getClass().getName());
        }

        log.debug("Dispatching query [{}] to handler [{}]", query.getClass().getSimpleName(), handler.getClass().getSimpleName());
        return handler.handle(query);
    }
}
