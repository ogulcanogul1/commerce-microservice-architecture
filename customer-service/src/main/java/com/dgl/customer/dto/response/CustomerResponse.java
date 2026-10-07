package com.dgl.customer.dto.response;

import com.dgl.customer.domain.CustomerStatus;

import java.time.Instant;
import java.util.UUID;

public record CustomerResponse(
    UUID id,
    String email,
    String firstName,
    String lastName,
    String phoneNumber,
    CustomerStatus status,
    PreferencesResponse preferences,
    Instant createdAt,
    Instant updatedAt
) {}
