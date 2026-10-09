package com.dgl.customer.controller;

import com.dgl.customer.dto.request.LoginRequest;
import com.dgl.customer.dto.request.OAuth2LoginRequest;
import com.dgl.customer.dto.request.RefreshTokenRequest;
import com.dgl.customer.dto.request.RegisterRequest;
import com.dgl.customer.dto.response.AuthResponse;
import com.dgl.customer.service.AuthService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.responses.ApiResponses;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/v1/auth")
@RequiredArgsConstructor
@Tag(name = "Authentication", description = "Endpoints for user registration, credential login, token refreshing, and OAuth2 social login")
public class AuthController {

    private final AuthService authService;

    @PostMapping("/register")
    @Operation(summary = "Register customer", description = "Creates a new customer account and issues an initial JWT token pair")
    @ApiResponses({
            @ApiResponse(responseCode = "201", description = "User registered successfully"),
            @ApiResponse(responseCode = "400", description = "Invalid registration data"),
            @ApiResponse(responseCode = "409", description = "Email already registered")
    })
    public ResponseEntity<AuthResponse> register(@Valid @RequestBody RegisterRequest request) {
        AuthResponse response = authService.register(request);
        return ResponseEntity.status(HttpStatus.CREATED).body(response);
    }

    @PostMapping("/login")
    @Operation(summary = "Login with credentials", description = "Authenticates using email and password, returning access and refresh JWT tokens")
    @ApiResponses({
            @ApiResponse(responseCode = "200", description = "Authentication successful"),
            @ApiResponse(responseCode = "401", description = "Invalid credentials")
    })
    public ResponseEntity<AuthResponse> login(@Valid @RequestBody LoginRequest request) {
        AuthResponse response = authService.login(request);
        return ResponseEntity.ok(response);
    }

    @PostMapping("/refresh")
    @Operation(summary = "Refresh access token", description = "Exchanges a valid refresh token for a fresh access token")
    @ApiResponses({
            @ApiResponse(responseCode = "200", description = "Token refreshed successfully"),
            @ApiResponse(responseCode = "401", description = "Expired or invalid refresh token")
    })
    public ResponseEntity<AuthResponse> refresh(@Valid @RequestBody RefreshTokenRequest request) {
        AuthResponse response = authService.refreshToken(request);
        return ResponseEntity.ok(response);
    }

    @PostMapping("/oauth2")
    @Operation(summary = "OAuth2 / Social login", description = "Authenticates or provisions user via OAuth2 provider token (Google, GitHub, etc.)")
    @ApiResponses({
            @ApiResponse(responseCode = "200", description = "OAuth2 authentication successful"),
            @ApiResponse(responseCode = "400", description = "Invalid provider payload")
    })
    public ResponseEntity<AuthResponse> oauth2Login(@Valid @RequestBody OAuth2LoginRequest request) {
        AuthResponse response = authService.oauth2Login(request);
        return ResponseEntity.ok(response);
    }
}
