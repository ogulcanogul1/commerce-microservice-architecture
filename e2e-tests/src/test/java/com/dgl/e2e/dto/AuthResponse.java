package com.dgl.e2e.dto;

public record AuthResponse(
        String accessToken,
        String refreshToken,
        String tokenType,
        long expiresIn,
        CustomerDto customer
) {}
