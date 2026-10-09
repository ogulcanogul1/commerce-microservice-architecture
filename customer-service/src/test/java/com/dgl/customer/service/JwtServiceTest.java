package com.dgl.customer.service;

import com.dgl.customer.domain.AuthProvider;
import com.dgl.customer.domain.Customer;
import com.dgl.customer.domain.CustomerStatus;
import com.dgl.customer.domain.Role;
import com.dgl.customer.exception.InvalidTokenException;
import io.jsonwebtoken.Claims;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class JwtServiceTest {

    private JwtService jwtService;
    private Customer sampleCustomer;
    private final UUID customerId = UUID.randomUUID();

    @BeforeEach
    void setUp() {
        jwtService = new JwtService(
                "super-secure-jwt-signing-secret-key-at-least-256-bits-long-32-chars",
                900000L,
                604800000L
        );

        sampleCustomer = Customer.builder()
                .id(customerId)
                .email("test.jwt@example.com")
                .firstName("Alice")
                .lastName("Smith")
                .role(Role.ROLE_CUSTOMER)
                .authProvider(AuthProvider.LOCAL)
                .status(CustomerStatus.ACTIVE)
                .build();
    }

    @Test
    @DisplayName("generateAccessToken: should contain expected claims and subject")
    void generateAccessToken_ShouldContainExpectedClaims() {
        String token = jwtService.generateAccessToken(sampleCustomer);

        assertThat(token).isNotBlank();
        Claims claims = jwtService.extractClaims(token);
        assertThat(claims.getSubject()).isEqualTo(customerId.toString());
        assertThat(claims.get("email")).isEqualTo("test.jwt@example.com");
        assertThat(claims.get("role")).isEqualTo("ROLE_CUSTOMER");
        assertThat(claims.get("authProvider")).isEqualTo("LOCAL");
        assertThat(claims.get("firstName")).isEqualTo("Alice");
        assertThat(claims.get("lastName")).isEqualTo("Smith");
        assertThat(claims.get("tokenType")).isEqualTo("ACCESS");
        assertThat(jwtService.isRefreshToken(token)).isFalse();
    }

    @Test
    @DisplayName("generateRefreshToken: should have tokenType REFRESH")
    void generateRefreshToken_ShouldHaveRefreshTokenClaim() {
        String refreshToken = jwtService.generateRefreshToken(sampleCustomer);

        assertThat(refreshToken).isNotBlank();
        assertThat(jwtService.isRefreshToken(refreshToken)).isTrue();
        assertThat(jwtService.extractCustomerId(refreshToken)).isEqualTo(customerId);
    }

    @Test
    @DisplayName("extractClaims: when token is tampered with, should throw InvalidTokenException")
    void extractClaims_WhenTamperedToken_ShouldThrowInvalidTokenException() {
        String token = jwtService.generateAccessToken(sampleCustomer);
        String tampered = token + "tampered";

        assertThatThrownBy(() -> jwtService.extractClaims(tampered))
                .isInstanceOf(InvalidTokenException.class);
    }
}
