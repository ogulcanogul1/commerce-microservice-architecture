package com.dgl.customer.service;

import com.dgl.customer.cqrs.CommandBus;
import com.dgl.customer.cqrs.command.LoginCommand;
import com.dgl.customer.cqrs.command.OAuth2LoginCommand;
import com.dgl.customer.cqrs.command.RefreshTokenCommand;
import com.dgl.customer.cqrs.command.RegisterCommand;
import com.dgl.customer.domain.AuthProvider;
import com.dgl.customer.dto.request.LoginRequest;
import com.dgl.customer.dto.request.OAuth2LoginRequest;
import com.dgl.customer.dto.request.RefreshTokenRequest;
import com.dgl.customer.dto.request.RegisterRequest;
import com.dgl.customer.dto.response.AuthResponse;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.*;

@ExtendWith(MockitoExtension.class)
class AuthServiceImplTest {

    @Mock
    private CommandBus commandBus;

    @InjectMocks
    private AuthServiceImpl authService;

    @Test
    @DisplayName("register: Should delegate to command bus")
    void register_shouldDelegate() {
        RegisterRequest request = new RegisterRequest("a@b.com", "P@ss1", "First", "Last", null);
        AuthResponse mockResponse = mock(AuthResponse.class);
        when(commandBus.execute(any(RegisterCommand.class))).thenReturn(mockResponse);

        AuthResponse actual = authService.register(request);

        assertThat(actual).isSameAs(mockResponse);
        verify(commandBus).execute(new RegisterCommand(request));
    }

    @Test
    @DisplayName("login: Should delegate to command bus")
    void login_shouldDelegate() {
        LoginRequest request = new LoginRequest("a@b.com", "P@ss1");
        AuthResponse mockResponse = mock(AuthResponse.class);
        when(commandBus.execute(any(LoginCommand.class))).thenReturn(mockResponse);

        AuthResponse actual = authService.login(request);

        assertThat(actual).isSameAs(mockResponse);
        verify(commandBus).execute(new LoginCommand(request));
    }

    @Test
    @DisplayName("refreshToken: Should delegate to command bus")
    void refreshToken_shouldDelegate() {
        RefreshTokenRequest request = new RefreshTokenRequest("ref_1");
        AuthResponse mockResponse = mock(AuthResponse.class);
        when(commandBus.execute(any(RefreshTokenCommand.class))).thenReturn(mockResponse);

        AuthResponse actual = authService.refreshToken(request);

        assertThat(actual).isSameAs(mockResponse);
        verify(commandBus).execute(new RefreshTokenCommand(request));
    }

    @Test
    @DisplayName("oauth2Login: Should delegate to command bus")
    void oauth2Login_shouldDelegate() {
        OAuth2LoginRequest request = new OAuth2LoginRequest(AuthProvider.GOOGLE, "g_1", "a@b.com", "First", "Last");
        AuthResponse mockResponse = mock(AuthResponse.class);
        when(commandBus.execute(any(OAuth2LoginCommand.class))).thenReturn(mockResponse);

        AuthResponse actual = authService.oauth2Login(request);

        assertThat(actual).isSameAs(mockResponse);
        verify(commandBus).execute(new OAuth2LoginCommand(request));
    }
}
