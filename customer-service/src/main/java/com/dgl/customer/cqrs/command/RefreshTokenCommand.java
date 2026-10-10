package com.dgl.customer.cqrs.command;

import com.dgl.customer.cqrs.Command;
import com.dgl.customer.dto.request.RefreshTokenRequest;
import com.dgl.customer.dto.response.AuthResponse;

public record RefreshTokenCommand(RefreshTokenRequest request) implements Command<AuthResponse> {
}
