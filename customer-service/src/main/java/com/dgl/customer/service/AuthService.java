package com.dgl.customer.service;

import com.dgl.customer.dto.request.LoginRequest;
import com.dgl.customer.dto.request.OAuth2LoginRequest;
import com.dgl.customer.dto.request.RefreshTokenRequest;
import com.dgl.customer.dto.request.RegisterRequest;
import com.dgl.customer.dto.response.AuthResponse;

public interface AuthService {
    AuthResponse register(RegisterRequest request);
    AuthResponse login(LoginRequest request);
    AuthResponse refreshToken(RefreshTokenRequest request);
    AuthResponse oauth2Login(OAuth2LoginRequest request);
}
