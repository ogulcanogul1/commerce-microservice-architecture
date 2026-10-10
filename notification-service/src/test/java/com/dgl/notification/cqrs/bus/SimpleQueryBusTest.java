package com.dgl.notification.cqrs.bus;

import com.dgl.notification.cqrs.Query;
import com.dgl.notification.cqrs.QueryHandler;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class SimpleQueryBusTest {

    record DummyQuery(String id) implements Query<String> {}
    record UnhandledQuery() implements Query<Void> {}

    static class DummyQueryHandler implements QueryHandler<DummyQuery, String> {
        @Override
        public String handle(DummyQuery query) {
            return "Found: " + query.id();
        }
    }

    @Test
    @DisplayName("execute: Should dispatch query to registered handler")
    void execute_shouldDispatchQueryToHandler() {
        DummyQueryHandler handler = new DummyQueryHandler();
        SimpleQueryBus bus = new SimpleQueryBus(List.of(handler));

        String result = bus.execute(new DummyQuery("notify-query-1"));

        assertThat(result).isEqualTo("Found: notify-query-1");
    }

    @Test
    @DisplayName("execute: Should throw IllegalStateException when no handler is registered")
    void execute_unregisteredQuery_shouldThrowException() {
        SimpleQueryBus bus = new SimpleQueryBus(List.of());

        assertThatThrownBy(() -> bus.execute(new UnhandledQuery()))
                .isInstanceOf(IllegalStateException.class)
                .hasMessageContaining("No QueryHandler registered");
    }

    @Test
    @DisplayName("execute: Should throw IllegalArgumentException when query is null")
    void execute_nullQuery_shouldThrowException() {
        SimpleQueryBus bus = new SimpleQueryBus(List.of());

        assertThatThrownBy(() -> bus.execute(null))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessageContaining("Query cannot be null");
    }
}
