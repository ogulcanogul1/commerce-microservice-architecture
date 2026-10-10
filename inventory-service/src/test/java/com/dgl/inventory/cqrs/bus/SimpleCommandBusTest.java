package com.dgl.inventory.cqrs.bus;

import com.dgl.inventory.cqrs.Command;
import com.dgl.inventory.cqrs.CommandHandler;
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
    @DisplayName("execute: Should dispatch command to registered handler")
    void execute_shouldDispatchCommandToHandler() {
        DummyCommandHandler handler = new DummyCommandHandler();
        SimpleCommandBus bus = new SimpleCommandBus(List.of(handler));

        String result = bus.execute(new DummyCommand("inv-test"));

        assertThat(result).isEqualTo("Handled: inv-test");
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
