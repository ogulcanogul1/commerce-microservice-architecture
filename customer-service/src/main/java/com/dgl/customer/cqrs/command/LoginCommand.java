package com.dgl.customer.cqrs.command;

import com.dgl.customer.cqrs.Command;
import com.dgl.customer.dto.request.LoginRequest;
import com.dgl.customer.dto.response.AuthResponse;

public record LoginCommand(LoginRequest request) implements Command<AuthResponse> {
}
