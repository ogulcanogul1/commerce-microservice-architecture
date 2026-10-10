package com.dgl.customer.cqrs.command;

import com.dgl.customer.cqrs.Command;
import com.dgl.customer.dto.request.OAuth2LoginRequest;
import com.dgl.customer.dto.response.AuthResponse;

public record OAuth2LoginCommand(OAuth2LoginRequest request) implements Command<AuthResponse> {
}
