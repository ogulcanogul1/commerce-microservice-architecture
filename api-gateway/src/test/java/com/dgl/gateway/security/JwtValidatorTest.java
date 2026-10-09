package com.dgl.gateway.security;

import io.jsonwebtoken.Claims;
import io.jsonwebtoken.JwtException;
import io.jsonwebtoken.Jwts;
import io.jsonwebtoken.security.Keys;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import javax.crypto.SecretKey;
import java.nio.charset.StandardCharsets;
import java.util.Date;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class JwtValidatorTest {

    private static final String SECRET = "dgl-super-secret-jwt-signing-key-commerce-platform-2026-secure";
    private JwtValidator jwtValidator;
    private SecretKey signingKey;

    @BeforeEach
    void setUp() {
        jwtValidator = new JwtValidator(SECRET);
        signingKey = Keys.hmacShaKeyFor(SECRET.getBytes(StandardCharsets.UTF_8));
    }

    @Test
    @DisplayName("validateAndExtractClaims: should extract claims from a valid token")
    void validateAndExtractClaims_WhenValidToken_ShouldExtractClaims() {
        String userId = UUID.randomUUID().toString();
        String token = Jwts.builder()
                .subject(userId)
                .claim("email", "user@example.com")
                .claim("role", "ROLE_CUSTOMER")
                .issuedAt(new Date())
                .expiration(new Date(System.currentTimeMillis() + 60000))
                .signWith(signingKey)
                .compact();

        Claims claims = jwtValidator.validateAndExtractClaims(token);

        assertThat(claims.getSubject()).isEqualTo(userId);
        assertThat(claims.get("email")).isEqualTo("user@example.com");
        assertThat(claims.get("role")).isEqualTo("ROLE_CUSTOMER");
    }

    @Test
    @DisplayName("validateAndExtractClaims: when token is expired, should throw JwtException")
    void validateAndExtractClaims_WhenExpiredToken_ShouldThrowJwtException() {
        String token = Jwts.builder()
                .subject("expired-user")
                .issuedAt(new Date(System.currentTimeMillis() - 120000))
                .expiration(new Date(System.currentTimeMillis() - 60000))
                .signWith(signingKey)
                .compact();

        assertThatThrownBy(() -> jwtValidator.validateAndExtractClaims(token))
                .isInstanceOf(JwtException.class);
    }

    @Test
    @DisplayName("validateAndExtractClaims: when token signature is invalid, should throw JwtException")
    void validateAndExtractClaims_WhenInvalidSignature_ShouldThrowJwtException() {
        SecretKey differentKey = Keys.hmacShaKeyFor("different-super-secret-key-that-is-at-least-256-bits".getBytes(StandardCharsets.UTF_8));
        String token = Jwts.builder()
                .subject("tampered-user")
                .issuedAt(new Date())
                .expiration(new Date(System.currentTimeMillis() + 60000))
                .signWith(differentKey)
                .compact();

        assertThatThrownBy(() -> jwtValidator.validateAndExtractClaims(token))
                .isInstanceOf(JwtException.class);
    }
}
