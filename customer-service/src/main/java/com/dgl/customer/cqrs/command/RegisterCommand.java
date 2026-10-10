package com.dgl.customer.cqrs.command;

import com.dgl.customer.cqrs.Command;
import com.dgl.customer.dto.request.RegisterRequest;
import com.dgl.customer.dto.response.AuthResponse;

public record RegisterCommand(RegisterRequest request) implements Command<AuthResponse> {
}
