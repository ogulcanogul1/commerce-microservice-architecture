package com.dgl.order.cqrs.bus;

import com.dgl.order.cqrs.Command;
import com.dgl.order.cqrs.CommandHandler;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class SimpleCommandBusTest {

    record DummyCommand(String payload) implements Command<String> {}
    record UnhandledCommand() implements Command<Void> {}

    static class DummyCommandHandler implements CommandHandler<DummyCommand, String> {
        @Override
        public String handle(DummyCommand command) {
            return "Handled: " + command.payload();
        }
    }

    @Test
    @DisplayName("execute: Should dispatch command to registered handler and return result")
    void execute_shouldDispatchCommandToHandler() {
        DummyCommandHandler handler = new DummyCommandHandler();
        SimpleCommandBus bus = new SimpleCommandBus(List.of(handler));

        String result = bus.execute(new DummyCommand("test-data"));

        assertThat(result).isEqualTo("Handled: test-data");
    }

    @Test
    @DisplayName("execute: Should throw IllegalStateException when no handler is registered")
    void execute_unregisteredCommand_shouldThrowException() {
        SimpleCommandBus bus = new SimpleCommandBus(List.of());

        assertThatThrownBy(() -> bus.execute(new UnhandledCommand()))
                .isInstanceOf(IllegalStateException.class)
                .hasMessageContaining("No CommandHandler registered");
    }

    @Test
    @DisplayName("execute: Should throw IllegalArgumentException when command is null")
    void execute_nullCommand_shouldThrowException() {
        SimpleCommandBus bus = new SimpleCommandBus(List.of());

        assertThatThrownBy(() -> bus.execute(null))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessageContaining("Command cannot be null");
    }
}
