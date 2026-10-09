package com.dgl.customer.dto.response;

public record AuthResponse(
        String accessToken,
        String refreshToken,
        String tokenType,
        long expiresIn,
        CustomerResponse customer
) {
    public static AuthResponse of(String accessToken, String refreshToken, long expiresIn, CustomerResponse customer) {
        return new AuthResponse(accessToken, refreshToken, "Bearer", expiresIn, customer);
    }
}
