package com.dgl.customer.dto.request;

import com.dgl.customer.domain.AuthProvider;
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

public record OAuth2LoginRequest(
        @NotNull(message = "Auth provider is required")
        AuthProvider provider,

        @NotBlank(message = "Provider user ID is required")
        String providerId,

        @NotBlank(message = "Email is required")
        @Email(message = "Email must be valid")
        String email,

        @NotBlank(message = "First name is required")
        String firstName,

        @NotBlank(message = "Last name is required")
        String lastName
) {}
