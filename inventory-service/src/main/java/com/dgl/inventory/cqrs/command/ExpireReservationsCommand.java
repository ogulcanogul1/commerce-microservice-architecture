package com.dgl.inventory.cqrs.command;

import com.dgl.inventory.cqrs.Command;

public record ExpireReservationsCommand() implements Command<Void> {
}
