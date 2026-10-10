package com.dgl.customer.controller;

import com.dgl.customer.cqrs.CommandBus;
import com.dgl.customer.cqrs.command.LoginCommand;
import com.dgl.customer.cqrs.command.OAuth2LoginCommand;
import com.dgl.customer.cqrs.command.RefreshTokenCommand;
import com.dgl.customer.cqrs.command.RegisterCommand;
import com.dgl.customer.domain.AuthProvider;
import com.dgl.customer.domain.CustomerStatus;
import com.dgl.customer.dto.request.LoginRequest;
import com.dgl.customer.dto.request.OAuth2LoginRequest;
import com.dgl.customer.dto.request.RefreshTokenRequest;
import com.dgl.customer.dto.request.RegisterRequest;
import com.dgl.customer.dto.response.AuthResponse;
import com.dgl.customer.dto.response.CustomerResponse;
import com.dgl.customer.exception.GlobalExceptionHandler;
import com.dgl.customer.exception.InvalidCredentialsException;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;

import java.time.Instant;
import java.util.UUID;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@ExtendWith(MockitoExtension.class)
class AuthControllerTest {

    private MockMvc mockMvc;

    @Mock
    private CommandBus commandBus;

    @InjectMocks
    private AuthController authController;

    private final ObjectMapper objectMapper = new ObjectMapper();

    private AuthResponse sampleAuthResponse;

    @BeforeEach
    void setUp() {
        mockMvc = MockMvcBuilders.standaloneSetup(authController)
                .setControllerAdvice(new GlobalExceptionHandler())
                .build();

        CustomerResponse customerResponse = new CustomerResponse(
                UUID.randomUUID(),
                "test@example.com",
                "Test",
                "User",
                null,
                CustomerStatus.ACTIVE,
                null,
                Instant.now(),
                Instant.now()
        );

        sampleAuthResponse = AuthResponse.of("access_token_123", "refresh_token_456", 900L, customerResponse);
    }

    @Test
    @DisplayName("POST /api/v1/auth/register: should return 201 Created and AuthResponse")
    void register_ShouldReturnCreated() throws Exception {
        RegisterRequest request = new RegisterRequest("test@example.com", "Password123!", "Test", "User", null);
        when(commandBus.execute(any(RegisterCommand.class))).thenReturn(sampleAuthResponse);

        mockMvc.perform(post("/api/v1/auth/register")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(request)))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.accessToken").value("access_token_123"))
                .andExpect(jsonPath("$.tokenType").value("Bearer"))
                .andExpect(jsonPath("$.customer.email").value("test@example.com"));

        verify(commandBus).execute(any(RegisterCommand.class));
    }

    @Test
    @DisplayName("POST /api/v1/auth/login: when valid credentials, should return 200 OK")
    void login_ShouldReturnOk() throws Exception {
        LoginRequest request = new LoginRequest("test@example.com", "Password123!");
        when(commandBus.execute(any(LoginCommand.class))).thenReturn(sampleAuthResponse);

        mockMvc.perform(post("/api/v1/auth/login")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(request)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.accessToken").value("access_token_123"))
                .andExpect(jsonPath("$.refreshToken").value("refresh_token_456"));

        verify(commandBus).execute(any(LoginCommand.class));
    }

    @Test
    @DisplayName("POST /api/v1/auth/login: when invalid credentials, should return 401 Unauthorized")
    void login_WhenInvalidCredentials_ShouldReturnUnauthorized() throws Exception {
        LoginRequest request = new LoginRequest("test@example.com", "WrongPassword");
        when(commandBus.execute(any(LoginCommand.class))).thenThrow(new InvalidCredentialsException());

        mockMvc.perform(post("/api/v1/auth/login")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(request)))
                .andExpect(status().isUnauthorized())
                .andExpect(jsonPath("$.title").value("Unauthorized"));

        verify(commandBus).execute(any(LoginCommand.class));
    }

    @Test
    @DisplayName("POST /api/v1/auth/refresh: when valid refresh token, should return 200 OK")
    void refresh_ShouldReturnOk() throws Exception {
        RefreshTokenRequest request = new RefreshTokenRequest("refresh_token_456");
        when(commandBus.execute(any(RefreshTokenCommand.class))).thenReturn(sampleAuthResponse);

        mockMvc.perform(post("/api/v1/auth/refresh")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(request)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.accessToken").value("access_token_123"));

        verify(commandBus).execute(any(RefreshTokenCommand.class));
    }

    @Test
    @DisplayName("POST /api/v1/auth/oauth2: when valid OAuth2 request, should return 200 OK")
    void oauth2Login_ShouldReturnOk() throws Exception {
        OAuth2LoginRequest request = new OAuth2LoginRequest(AuthProvider.GOOGLE, "gid_123", "test@example.com", "Test", "User");
        when(commandBus.execute(any(OAuth2LoginCommand.class))).thenReturn(sampleAuthResponse);

        mockMvc.perform(post("/api/v1/auth/oauth2")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(request)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.accessToken").value("access_token_123"));

        verify(commandBus).execute(any(OAuth2LoginCommand.class));
    }
}
