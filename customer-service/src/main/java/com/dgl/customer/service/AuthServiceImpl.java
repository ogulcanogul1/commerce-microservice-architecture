package com.dgl.customer.service;

import com.dgl.customer.cqrs.CommandBus;
import com.dgl.customer.cqrs.command.LoginCommand;
import com.dgl.customer.cqrs.command.OAuth2LoginCommand;
import com.dgl.customer.cqrs.command.RefreshTokenCommand;
import com.dgl.customer.cqrs.command.RegisterCommand;
import com.dgl.customer.dto.request.LoginRequest;
import com.dgl.customer.dto.request.OAuth2LoginRequest;
import com.dgl.customer.dto.request.RefreshTokenRequest;
import com.dgl.customer.dto.request.RegisterRequest;
import com.dgl.customer.dto.response.AuthResponse;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;

@Service
@RequiredArgsConstructor
public class AuthServiceImpl implements AuthService {

    private final CommandBus commandBus;

    @Override
    public AuthResponse register(RegisterRequest request) {
        return commandBus.execute(new RegisterCommand(request));
    }

    @Override
    public AuthResponse login(LoginRequest request) {
        return commandBus.execute(new LoginCommand(request));
    }

    @Override
    public AuthResponse refreshToken(RefreshTokenRequest request) {
        return commandBus.execute(new RefreshTokenCommand(request));
    }

    @Override
    public AuthResponse oauth2Login(OAuth2LoginRequest request) {
        return commandBus.execute(new OAuth2LoginCommand(request));
    }
}
